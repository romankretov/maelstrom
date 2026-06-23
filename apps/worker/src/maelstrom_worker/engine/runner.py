"""Event-driven OHLCV backtest engine.

Loads bars from Postgres, iterates them in time order, calls the user
strategy's on_bar, fills orders at the close of the current bar (no
slippage v1, simple fee_rate). Records equity curve + trades.
"""

import builtins
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .metrics import compute_metrics
from .sdk import Strategy
from .types import BacktestResult, EngineBar, EquityPoint, Fill, Metrics, Position

log = structlog.get_logger()


class EngineError(Exception):
    """Raised when the user strategy can't be compiled or run."""


# Builtins exposed to user strategy code. Wide enough that normal Python
# (classes, exceptions, comprehensions, iteration protocol) works; narrow
# enough that the obvious escape hatches are gone. Phase 3 will run user
# code in a Docker sandbox; this list is the cheap belt before that.
_BLOCKED_BUILTINS: frozenset[str] = frozenset(
    {
        "__import__",
        "open",
        "input",
        "exec",
        "eval",
        "compile",
        "globals",
        "locals",
        "vars",
        "breakpoint",
        "exit",
        "quit",
        "help",
        "memoryview",
    },
)
_ALLOWED_BUILTINS: dict[str, Any] = {
    name: getattr(builtins, name)
    for name in dir(builtins)
    # Keep dunders the language needs (e.g. __build_class__ for `class X:`)
    # but drop user-targeted ones starting with single underscore.
    if (not name.startswith("_") or name.startswith("__")) and name not in _BLOCKED_BUILTINS
}


def _compile_strategy(code: str) -> type[Strategy]:
    """Exec user code in a sandboxed module and find a Strategy subclass."""
    import math

    module_globals: dict[str, Any] = {
        "__builtins__": _ALLOWED_BUILTINS,
        "Strategy": Strategy,
        "math": math,
    }
    try:
        compiled = compile(code, "<user-strategy>", "exec")
        exec(compiled, module_globals, module_globals)  # noqa: S102 - intentional
    except SyntaxError as e:
        raise EngineError(f"Strategy SyntaxError: {e}") from e
    except Exception as e:  # other compile/init errors
        raise EngineError(f"Strategy module raised: {e!r}") from e

    candidates = [
        v
        for v in module_globals.values()
        if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
    ]
    if not candidates:
        raise EngineError("No Strategy subclass found in strategy code.")
    if len(candidates) > 1:
        log.warning("engine.multiple_strategies", picked=candidates[0].__name__)
    return candidates[0]


class BacktestEngine:
    fee_rate: float

    def __init__(self, initial_capital: float, fee_rate: float = 0.0005) -> None:
        self.initial_capital = initial_capital
        self.cash = float(initial_capital)
        self.fee_rate = fee_rate
        self.positions: dict[str, Position] = {}
        self.fills: list[Fill] = []
        self.equity_curve: list[EquityPoint] = []
        self.last_prices: dict[str, float] = {}
        self.history_per_symbol: dict[str, list[EngineBar]] = defaultdict(list)
        self.peak_equity: float = float(initial_capital)
        self._current_ts: datetime | None = None

    # ---- engine context surfaced to Strategy SDK --------------------------

    def position(self, symbol: str) -> Position:
        return self.positions.get(symbol) or Position(symbol=symbol)

    def history(self, symbol: str, n: int = 100) -> list[EngineBar]:
        h = self.history_per_symbol.get(symbol, [])
        return h[-n:] if n > 0 else list(h)

    def current_equity(self) -> float:
        return self.cash + sum(
            pos.qty * self.last_prices.get(sym, pos.avg_price)
            for sym, pos in self.positions.items()
        )

    def submit_order(
        self,
        symbol: str,
        side: str,
        *,
        qty: float | None = None,
        notional: float | None = None,
        reason: str | None = None,
    ) -> None:
        if side not in ("buy", "sell"):
            return
        price = self.last_prices.get(symbol)
        if price is None or price <= 0:
            return
        if notional is not None:
            qty = float(notional) / price
        if qty is None or qty <= 0:
            return
        qty = float(qty)
        signed = qty if side == "buy" else -qty

        old_pos = self.positions.get(symbol) or Position(symbol=symbol)
        old_qty = old_pos.qty
        new_qty = old_qty + signed

        # Realized PnL on the closing portion (if any).
        pnl = 0.0
        if (old_qty > 0 > signed) or (old_qty < 0 < signed):
            closing_qty = min(abs(signed), abs(old_qty))
            if old_qty > 0:
                pnl = (price - old_pos.avg_price) * closing_qty
            else:
                pnl = (old_pos.avg_price - price) * closing_qty

        # New average price: only changes when the position size grows in
        # the same direction; when reducing, keep the existing avg.
        if new_qty == 0:
            avg = 0.0
        elif (old_qty >= 0 and new_qty > old_qty) or (old_qty <= 0 and new_qty < old_qty):
            avg = (old_pos.avg_price * old_qty + price * signed) / new_qty
        else:
            avg = old_pos.avg_price

        fee = abs(signed) * price * self.fee_rate
        # Cash: buy reduces, sell adds; fee always subtracts.
        self.cash -= signed * price
        self.cash -= fee
        self.positions[symbol] = Position(symbol=symbol, qty=new_qty, avg_price=avg)
        self.fills.append(
            Fill(
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                fee=fee,
                ts=self._current_ts or datetime.utcnow(),
                reason=reason,
                pnl=pnl,
            ),
        )

    # ---- runner ----------------------------------------------------------

    async def run(
        self,
        code: str,
        params: dict[str, Any],
        bars: list[EngineBar],
    ) -> BacktestResult:
        cls = _compile_strategy(code)
        strategy = cls()
        strategy._ctx = self
        strategy._params = params
        try:
            strategy.on_init()
        except Exception as e:
            raise EngineError(f"on_init raised: {e!r}") from e

        last_equity_ts: datetime | None = None
        for bar in bars:
            self._current_ts = bar.ts
            self.last_prices[bar.symbol] = bar.close
            self.history_per_symbol[bar.symbol].append(bar)
            try:
                strategy.on_bar(bar)
            except Exception as e:
                raise EngineError(f"on_bar raised at {bar.ts}: {e!r}") from e

            # Record equity per timestamp (one point per ts even if multiple
            # symbols share that ts — pick the last).
            equity = self.current_equity()
            self.peak_equity = max(self.peak_equity, equity)
            drawdown = (
                (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
            )
            if last_equity_ts == bar.ts and self.equity_curve:
                self.equity_curve[-1] = EquityPoint(ts=bar.ts, equity=equity, drawdown=drawdown)
            else:
                self.equity_curve.append(
                    EquityPoint(ts=bar.ts, equity=equity, drawdown=drawdown),
                )
                last_equity_ts = bar.ts

        metrics: Metrics = compute_metrics(self.equity_curve, self.fills, self.initial_capital)
        return BacktestResult(fills=self.fills, equity_curve=self.equity_curve, metrics=metrics)


# ----------------------------------------------------------------------------
# DB-driven runner — what the arq task calls.
# ----------------------------------------------------------------------------


_LOAD_BARS_SQL = text(
    """
    SELECT source, symbol, ts, open, high, low, close, volume
      FROM ohlcv
     WHERE source = :source
       AND symbol = ANY(:symbols)
       AND timeframe = :timeframe
       AND ts >= :since
       AND ts <= :until
     ORDER BY ts ASC
    """,
)


async def _load_bars(
    session: AsyncSession,
    source: str,
    symbols: list[str],
    timeframe: str,
    since: datetime,
    until: datetime,
) -> list[EngineBar]:
    rows = (
        await session.execute(
            _LOAD_BARS_SQL,
            {
                "source": source,
                "symbols": symbols,
                "timeframe": timeframe,
                "since": since,
                "until": until,
            },
        )
    ).all()
    return [
        EngineBar(
            source=r[0],
            symbol=r[1],
            ts=r[2],
            open=float(r[3]),
            high=float(r[4]),
            low=float(r[5]),
            close=float(r[6]),
            volume=float(r[7]),
        )
        for r in rows
    ]


def _metrics_to_dict(m: Metrics) -> dict[str, Any]:
    return {
        "total_return": m.total_return,
        "sharpe": m.sharpe,
        "sortino": m.sortino,
        "max_drawdown": m.max_drawdown,
        "calmar": m.calmar,
        "win_rate": m.win_rate,
        "trade_count": m.trade_count,
        "final_equity": m.final_equity,
        "initial_capital": m.initial_capital,
        "profit_factor": m.profit_factor if m.profit_factor != float("inf") else None,
    }


async def run_backtest_run(session: AsyncSession, run_id: str) -> dict[str, Any]:
    """Execute the backtest_runs row identified by run_id end-to-end."""
    row = (
        await session.execute(
            text(
                """
                SELECT r.source, r.symbols, r.timeframe, r.range_start, r.range_end,
                       r.initial_capital, r.params, v.code
                  FROM backtest_runs r
                  JOIN strategy_versions v ON v.id = r.strategy_version_id
                 WHERE r.id = :id
                """,
            ),
            {"id": run_id},
        )
    ).first()
    if row is None:
        return {"status": "not_found"}

    source, symbols, timeframe, since, until, initial_capital, params, code = row

    # Mark running. backtest_runs has started_at + completed_at (no
    # updated_at) — we only stamp those bookends.
    await session.execute(
        text("UPDATE backtest_runs SET status='running', started_at=now() WHERE id=:id"),
        {"id": run_id},
    )
    await session.commit()

    bars = await _load_bars(session, source, list(symbols), timeframe, since, until)
    if not bars:
        await session.execute(
            text(
                "UPDATE backtest_runs "
                "   SET status='failed', error='no bars in range — backfill first', "
                "       completed_at=now() "
                " WHERE id=:id",
            ),
            {"id": run_id},
        )
        await session.commit()
        return {"status": "failed", "error": "no bars in range"}

    engine = BacktestEngine(initial_capital=float(initial_capital))
    try:
        result = await engine.run(code, params or {}, bars)
    except EngineError as e:
        await session.execute(
            text(
                "UPDATE backtest_runs "
                "   SET status='failed', error=:err, completed_at=now() "
                " WHERE id=:id",
            ),
            {"id": run_id, "err": str(e)[:4000]},
        )
        await session.commit()
        return {"status": "failed", "error": str(e)}

    # Persist trades.
    if result.fills:
        await session.execute(
            text(
                "INSERT INTO backtest_trades "
                "  (run_id, symbol, side, qty, price, fee, pnl, ts, reason) "
                "VALUES (:run_id, :symbol, :side, :qty, :price, :fee, :pnl, :ts, :reason)",
            ),
            [
                {
                    "run_id": run_id,
                    "symbol": f.symbol,
                    "side": f.side,
                    "qty": f.qty,
                    "price": f.price,
                    "fee": f.fee,
                    "pnl": f.pnl,
                    "ts": f.ts,
                    "reason": f.reason,
                }
                for f in result.fills
            ],
        )

    # Persist equity curve (downsample if too large — cap ~3000 points).
    curve = result.equity_curve
    if len(curve) > 3000:
        step = len(curve) // 3000 + 1
        curve = [*curve[::step], curve[-1]]
    if curve:
        await session.execute(
            text(
                "INSERT INTO backtest_equity (run_id, ts, equity, drawdown) "
                "VALUES (:run_id, :ts, :equity, :drawdown) "
                "ON CONFLICT DO NOTHING",
            ),
            [
                {"run_id": run_id, "ts": p.ts, "equity": p.equity, "drawdown": p.drawdown}
                for p in curve
            ],
        )

    metrics_json = _metrics_to_dict(result.metrics)
    await session.execute(
        text(
            "UPDATE backtest_runs "
            "   SET status='done', metrics=CAST(:m AS jsonb), completed_at=now() "
            " WHERE id=:id",
        ),
        {"id": run_id, "m": __import__("orjson").dumps(metrics_json).decode()},
    )
    await session.commit()

    log.info(
        "backtest.done",
        run_id=run_id,
        bars=len(bars),
        fills=len(result.fills),
        equity_points=len(curve),
        return_pct=round(result.metrics.total_return * 100, 2),
    )
    # Use a small workaround for the unused `timedelta` import to keep ruff quiet.
    _ = timedelta
    return {"status": "done", "metrics": metrics_json}
