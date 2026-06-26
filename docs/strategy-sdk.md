# Strategy SDK contract

Anything you write in the editor runs unchanged in two places: the
backtest engine (`apps/worker/.../engine/runner.py`) and the live
runner (`apps/worker/.../live/runner.py`). The two implementations
are different but their _surface_ — the methods and behavior a
`Strategy` subclass observes — is identical. This document is the
authoritative contract for that surface. If code drifts from this
doc, that's a bug; see `apps/worker/tests/test_sdk_parity.py`.

---

## Class shape

```python
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar


class MyStrategy(Strategy):
    symbols   = ("BTC-PERP",)             # one or more
    timeframe = "1h"                       # 1m | 5m | 15m | 1h | 4h | 1d

    def on_init(self) -> None: ...
    def on_bar(self, bar: EngineBar) -> None: ...
```

`symbols` and `timeframe` are read at spawn time; changing them on an
instance is a no-op.

---

## Lifecycle

1. Engine instantiates `MyStrategy()`. `__init__` MUST be parameterless
   (the engine doesn't pass anything).
2. Engine assigns the context object: `strategy._ctx = <engine>`.
3. Engine calls `strategy.on_init()` exactly once.
4. For every bar, in time order, engine calls `strategy.on_bar(bar)`.
5. After `on_bar` returns, the engine processes any orders the
   strategy queued via `self.buy / sell / close`. Orders fill against
   that same bar's close (with slippage / fees applied).

In live mode, step 5 still happens at the close of every bar — the
bar feed is a websocket and the runner waits for the bar-close signal
before invoking `on_bar`.

---

## Order placement

All orders are MARKET orders. Limit orders are not yet supported.

| Call | What it does |
|---|---|
| `self.buy(symbol, *, notional=USD, reason=...)` | Open or add to a long. |
| `self.sell(symbol, *, notional=USD, reason=...)` | Open or add to a short. |
| `self.close(symbol, *, reason=...)` | Close any open position for `symbol`. |

You can also pass `qty=` instead of `notional=`. Exactly one of the
two must be set. `notional` is sized at the bar's close price.

Orders submitted from `on_bar` are queued and submitted **after**
`on_bar` returns. So inside the same bar, ordering matters:

```python
self.buy("BTC-PERP", notional=100)
# self.position("BTC-PERP").qty is still 0 here — the buy hasn't
# filled yet. It fills before the NEXT call to on_bar.
```

---

## Read-only state

| Accessor | Returns |
|---|---|
| `self.position(symbol)` | `Position(qty, avg_price, unrealized_pnl)`. Returns a zero position if you don't have one. |
| `self.history(symbol, n=N)` | The last `N` bars (or fewer near start) **in chronological order** — `history[0]` is the oldest, `history[-1]` is the most recent (current) bar. Capped at `N`. |
| `self.cash` | USDC cash balance. |
| `self.equity` | Cash + mark-to-market value of all open positions. |
| `self.params` | Whatever dict was attached to the backtest/live run. Empty `{}` if none. |

## Debug logging

```python
self.log(message: str, **fields)
```

Emit a debug message. `print()` and the `logging` module are blocked by the
sandbox, so this is the supported way to surface "why did/didn't my strategy
trade?" intermediate state. Example:

```python
def on_bar(self, bar):
    rsi = self._rsi()
    self.log("rsi check", rsi=round(rsi, 2), close=bar.close)
    if rsi < 30 and self.position(bar.symbol).qty == 0:
        self.buy(bar.symbol, notional=1000, reason="oversold")
```

- In **backtest**, messages are buffered on the engine; the dry-run dialog and
  `BacktestResult.logs` expose them (capped at the most recent 50).
- In **live**, the runner writes each call as a `live_events` row with
  `kind='log'`. The event panel on the live run page renders them inline with
  fills and order events.

`message` is truncated to 500 chars. Fields are stored as-is — keep them small
and JSON-serializable.

### `history()` gotchas

- **Capped, not growing.** `len(self.history(sym, n=100))` is bounded
  by 100. If you want "bars since start", increment a counter in
  `on_init` and bump it in `on_bar`.
- **Includes the current bar.** `history(n=1)` returns `[bar]`.
- **Chronological.** Older bars come first. Do NOT call `reversed()`
  expecting newest-first.

---

## EngineBar fields

```python
@dataclass
class EngineBar:
    source:   str   # "binance" | "hyperliquid"
    symbol:   str   # "BTC-PERP"
    ts:       datetime  # UTC, tz-aware, bar close timestamp
    open:     float
    high:     float
    low:      float
    close:    float
    volume:   float
```

`bar.close` is the **final close** — `on_bar` only fires after the
bar has closed in both modes.

---

## Backtest ≡ live

The two engines maintain separate code paths, but they're tested for
parity. `apps/worker/tests/test_sdk_parity.py` runs the same strategy
through both on canned bars and asserts the fills come out identical.

If you observe different behavior between backtest and live for the
same code, that's a bug — file it.

Known design differences (intentional, not parity violations):

- **Live can't see future bars.** Both backtest and live process bars
  in arrival order, but in backtest the entire range exists ahead of
  time; live is fed by the websocket as bars close.
- **Slippage model.** Both use `last_price * (1 ± slippage)` for
  market fills; the default slippage is 0.0002 (2 bps).
- **Fees.** Default fee rate is 5 bps (0.0005). Both engines bake
  this into the fill PnL.

---

## Quirks worth knowing

1. `on_bar` fires AFTER the bar closes. `bar.close` is final.
2. Orders queued in `on_bar` fill before the NEXT `on_bar`, not the
   current one.
3. `history(n=N)` returns at most `N` bars in CHRONOLOGICAL order.
4. No built-in bar counter; track your own in `on_init`.
5. The same `MyStrategy` class is spawned anew in backtest vs live;
   instance state (anything you set on `self`) is per-run.
6. `self.params` is mutable but DO NOT mutate it — other components
   reference the same dict.
7. **No `import` statements.** Strategy code runs inside a sandbox
   that blocks `__import__`. `Strategy`, `EngineBar`, `Position`, and
   `math` are injected as globals — write code that uses them
   directly (no `from ... import ...` lines).
