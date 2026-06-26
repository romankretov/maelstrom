"""User-facing SDK. User strategies subclass `Strategy` and implement on_bar.

The runner injects the engine context as `self._ctx` before any callbacks
fire — that's how `self.buy(...)` and friends route into the engine.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from .types import EngineBar, Position

if TYPE_CHECKING:
    from .runner import BacktestEngine


class Strategy:
    """Subclass and set `symbols` + `timeframe`. Override `on_bar`.

    Helpers available to subclasses:
        self.buy(symbol, qty=..., notional=..., reason=...)
        self.sell(symbol, qty=..., notional=..., reason=...)
        self.close(symbol, reason=...)
        self.position(symbol) -> Position
        self.history(symbol, n=100) -> list[EngineBar]   # oldest -> newest
        self.cash -> float
        self.equity -> float
        self.params -> dict[str, Any]
    """

    symbols: Sequence[str] = ()
    timeframe: str = "1h"

    # Engine-provided plumbing — never set by user code.
    _ctx: "BacktestEngine"
    _params: dict[str, Any]

    def on_init(self) -> None:
        """Called once before the first bar."""

    def on_bar(self, bar: EngineBar) -> None:
        """Called for every bar in time order. Implement in your subclass."""

    # ---- order placement --------------------------------------------------

    def buy(
        self,
        symbol: str,
        *,
        qty: float | None = None,
        notional: float | None = None,
        reason: str | None = None,
    ) -> None:
        self._ctx.submit_order(symbol, "buy", qty=qty, notional=notional, reason=reason)

    def sell(
        self,
        symbol: str,
        *,
        qty: float | None = None,
        notional: float | None = None,
        reason: str | None = None,
    ) -> None:
        self._ctx.submit_order(symbol, "sell", qty=qty, notional=notional, reason=reason)

    def close(self, symbol: str, *, reason: str | None = None) -> None:
        pos = self.position(symbol)
        if pos.qty > 0:
            self.sell(symbol, qty=pos.qty, reason=reason or "close-long")
        elif pos.qty < 0:
            self.buy(symbol, qty=-pos.qty, reason=reason or "close-short")

    def log(self, message: str, **fields: Any) -> None:
        """Emit a log message that surfaces in the live runtime event panel
        and in dry-run results. Use this for strategy-side debugging:

            self.log("rsi crossed 30", rsi=29.8)

        In backtest, messages are buffered on the engine and exposed via
        BacktestResult.logs. In live, the runner persists them to
        live_events with kind='log'."""
        self._ctx.emit_log(message[:500], fields)

    # ---- state ------------------------------------------------------------

    def position(self, symbol: str) -> Position:
        return self._ctx.position(symbol)

    def history(self, symbol: str, n: int = 100) -> list[EngineBar]:
        return self._ctx.history(symbol, n)

    @property
    def cash(self) -> float:
        return self._ctx.cash

    @property
    def equity(self) -> float:
        return self._ctx.current_equity()

    @property
    def params(self) -> dict[str, Any]:
        return self._params
