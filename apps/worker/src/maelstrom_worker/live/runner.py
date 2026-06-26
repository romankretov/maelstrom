"""Live runner: one task per live_strategies row. Subscribes to Redis bar
stream, dispatches each bar to the user strategy, routes orders through
the broker, marks positions to market, persists periodic equity samples.

User strategy code is the same Strategy subclass that backtest runs —
self.buy/sell/close/position/history all work; orders just go to a real
table instead of an in-memory list.
"""

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any, cast

import orjson
import redis.asyncio as aioredis
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from maelstrom_worker.broker import Broker, OrderIntent
from maelstrom_worker.engine.runner import _compile_strategy
from maelstrom_worker.engine.sdk import Strategy
from maelstrom_worker.engine.types import EngineBar, Position

log = structlog.get_logger()


# Per-symbol history depth fed to the strategy.
HISTORY_DEPTH = 2000

# How often (in bars) to write an equity snapshot.
EQUITY_EVERY_N_BARS = 60


class LiveContext:
    """Strategy SDK glue. Same shape as the BacktestEngine context."""

    def __init__(
        self,
        live_strategy_id: str,
        account_id: str,
        source: str,
        broker: Broker,
        session_maker: async_sessionmaker,
    ) -> None:
        self.live_strategy_id = live_strategy_id
        self.account_id = account_id
        self.source = source
        self.broker = broker
        self.sm = session_maker
        # Per-symbol cached state — kept fresh as fills land.
        self.last_prices: dict[str, float] = {}
        self.history_per_symbol: dict[str, deque[EngineBar]] = defaultdict(
            lambda: deque(maxlen=HISTORY_DEPTH),
        )
        self.positions: dict[str, Position] = {}
        self.starting_capital: float = 0.0
        self.realized_pnl: float = 0.0
        # Filled by Strategy.buy/sell via the SDK; flushed after on_bar.
        self.pending_intents: list[OrderIntent] = []
        # Filled by Strategy.log(); flushed after on_bar.
        self.pending_log_entries: list[dict[str, Any]] = []

    # ---- Strategy SDK surface --------------------------------------------

    def position(self, symbol: str) -> Position:
        return self.positions.get(symbol) or Position(symbol=symbol)

    def history(self, symbol: str, n: int = 100) -> list[EngineBar]:
        h = self.history_per_symbol.get(symbol)
        if not h:
            return []
        return list(h)[-n:] if n > 0 else list(h)

    def current_equity(self) -> float:
        # cash + sum(qty * last_price). cash = starting + realized - fees baked in.
        position_value = sum(
            pos.qty * self.last_prices.get(sym, pos.avg_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + position_value

    @property
    def cash(self) -> float:
        # Cash = starting + realized_pnl - sum(open position cost)
        # Open position cost = sum(qty * avg_price), since fees were absorbed
        # into realized_pnl by the broker's accounting.
        open_cost = sum(pos.qty * pos.avg_price for pos in self.positions.values())
        return self.starting_capital + self.realized_pnl - open_cost

    def emit_log(self, message: str, fields: dict[str, Any]) -> None:
        """SDK hook for self.log(...). Queue the message for the runner's
        per-bar drain so we don't open a DB session inside on_bar."""
        self.pending_log_entries.append({"message": message, "fields": fields})

    def submit_order(
        self,
        symbol: str,
        side: str,
        *,
        qty: float | None = None,
        notional: float | None = None,
        reason: str | None = None,
    ) -> None:
        self.pending_intents.append(
            OrderIntent(
                account_id=self.account_id,
                live_strategy_id=self.live_strategy_id,
                source=self.source,
                symbol=symbol,
                side=side,
                qty=qty,
                notional=notional,
                reason=reason,
                idempotency_key=f"{self.live_strategy_id}:{symbol}:{datetime.now(UTC).timestamp():.6f}",
            ),
        )

    # ---- bookkeeping called by the runner --------------------------------

    async def hydrate_from_db(self) -> None:
        async with self.sm() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT symbol, qty, avg_price, realized_pnl, last_price "
                        "FROM positions WHERE account_id = :acc",
                    ),
                    {"acc": self.account_id},
                )
            ).all()
        for sym, qty, avg_price, real_pnl, last_price in rows:
            self.positions[sym] = Position(
                symbol=sym,
                qty=float(qty),
                avg_price=float(avg_price),
            )
            self.realized_pnl += float(real_pnl)
            if last_price and float(last_price) > 0:
                self.last_prices[sym] = float(last_price)

    def apply_fill(
        self,
        symbol: str,
        signed_qty: float,
        fill_price: float,
        pnl: float,
    ) -> None:
        old = self.positions.get(symbol) or Position(symbol=symbol)
        new_qty = old.qty + signed_qty
        if new_qty == 0:
            new_avg = 0.0
        elif (old.qty >= 0 and new_qty > old.qty) or (old.qty <= 0 and new_qty < old.qty):
            new_avg = (old.avg_price * old.qty + fill_price * signed_qty) / new_qty
        else:
            new_avg = old.avg_price
        self.positions[symbol] = Position(symbol=symbol, qty=new_qty, avg_price=new_avg)
        self.realized_pnl += pnl


class LiveRunner:
    def __init__(
        self,
        live_strategy_id: str,
        broker: Broker,
        session_maker: async_sessionmaker,
        redis_client: aioredis.Redis,
    ) -> None:
        self.live_strategy_id = live_strategy_id
        self.broker = broker
        self.sm = session_maker
        self.redis = redis_client
        self._stopped = asyncio.Event()
        self._bar_count = 0

    async def _load_config(self) -> dict[str, Any]:
        async with self.sm() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT ls.account_id, ls.source, ls.symbols, ls.timeframe,
                               ls.params, sv.code, a.starting_capital
                          FROM live_strategies ls
                          JOIN strategy_versions sv ON sv.id = ls.strategy_version_id
                          JOIN accounts a ON a.id = ls.account_id
                         WHERE ls.id = :id
                        """,
                    ),
                    {"id": self.live_strategy_id},
                )
            ).first()
        if row is None:
            raise RuntimeError(f"live_strategy {self.live_strategy_id} not found")
        return {
            "account_id": str(row[0]),
            "source": row[1],
            "symbols": list(row[2]),
            "timeframe": row[3],
            "params": row[4] or {},
            "code": row[5],
            "starting_capital": float(row[6]),
        }

    async def _emit_event(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a row to live_events. Best-effort — never raises."""
        try:
            async with self.sm() as session:
                await session.execute(
                    text(
                        "INSERT INTO live_events (live_strategy_id, kind, payload) "
                        "VALUES (:lsid, :kind, CAST(:payload AS jsonb))",
                    ),
                    {
                        "lsid": self.live_strategy_id,
                        "kind": kind[:32],
                        "payload": orjson.dumps(payload or {}).decode("utf-8"),
                    },
                )
                await session.commit()
        except Exception as e:
            log.warning("live.event.persist_failed", error=str(e))

    async def _set_status(self, status: str, error: str | None = None) -> None:
        # asyncpg can't deduce a single type for a bind param reused across
        # a varchar column assignment AND text-literal comparisons. Precompute
        # the timestamp-affecting booleans in Python so each named param is
        # used in exactly one context.
        is_running = status == "running"
        is_terminal = status in ("stopped", "failed")
        sql = (
            "UPDATE live_strategies "
            "   SET status     = :status, "
            "       error      = :error, "
            "       updated_at = now(), "
            "       started_at = CASE "
            "                      WHEN :is_running AND started_at IS NULL THEN now() "
            "                      ELSE started_at "
            "                    END, "
            "       stopped_at = CASE "
            "                      WHEN :is_terminal THEN now() "
            "                      ELSE stopped_at "
            "                    END "
            " WHERE id = :id"
        )
        async with self.sm() as session:
            await session.execute(
                text(sql),
                {
                    "id": self.live_strategy_id,
                    "status": status,
                    "error": error,
                    "is_running": is_running,
                    "is_terminal": is_terminal,
                },
            )
            await session.commit()

    async def run(self) -> None:
        try:
            config = await self._load_config()
        except Exception as e:
            log.exception("live.config_load_failed", id=self.live_strategy_id, error=str(e))
            await self._set_status("failed", error=str(e)[:2000])
            return

        try:
            cls = _compile_strategy(config["code"])
        except Exception as e:
            log.exception("live.compile_failed", id=self.live_strategy_id, error=str(e))
            await self._set_status("failed", error=str(e)[:2000])
            return

        ctx = LiveContext(
            live_strategy_id=self.live_strategy_id,
            account_id=config["account_id"],
            source=config["source"],
            broker=self.broker,
            session_maker=self.sm,
        )
        ctx.starting_capital = config["starting_capital"]
        await ctx.hydrate_from_db()

        strategy = cls()
        strategy._ctx = cast(Any, ctx)
        strategy._params = config["params"]
        try:
            strategy.on_init()
        except Exception as e:
            log.exception("live.on_init_failed", id=self.live_strategy_id)
            await self._set_status("failed", error=f"on_init: {e!r}"[:2000])
            return

        # Preload bar history per symbol so SMAs etc. have signal on day one.
        await self._preload_history(
            ctx,
            source=config["source"],
            symbols=config["symbols"],
            timeframe=config["timeframe"],
        )

        await self._set_status("running")
        log.info(
            "live.start",
            id=self.live_strategy_id,
            source=config["source"],
            symbols=config["symbols"],
            tf=config["timeframe"],
        )

        pubsub = self.redis.pubsub()
        channels = [
            f"bars:{config['source']}:{sym}:{config['timeframe']}" for sym in config["symbols"]
        ]
        await pubsub.subscribe(*channels)
        try:
            async for msg in pubsub.listen():
                if self._stopped.is_set():
                    break
                if msg["type"] != "message":
                    continue
                try:
                    payload = orjson.loads(msg["data"])
                    bar = EngineBar(
                        source=payload["source"],
                        symbol=payload["symbol"],
                        ts=datetime.fromisoformat(payload["ts"]),
                        open=payload["open"],
                        high=payload["high"],
                        low=payload["low"],
                        close=payload["close"],
                        volume=payload["volume"],
                    )
                except Exception as e:
                    log.warning("live.bad_bar", id=self.live_strategy_id, error=str(e))
                    continue

                await self._handle_bar(ctx, strategy, bar)
                self._bar_count += 1
                if self._bar_count % EQUITY_EVERY_N_BARS == 0:
                    await self._persist_equity(ctx)
        except asyncio.CancelledError:
            log.info("live.cancelled", id=self.live_strategy_id)
        except Exception as e:
            log.exception("live.crashed", id=self.live_strategy_id, error=str(e))
            await self._set_status("failed", error=str(e)[:2000])
            return
        finally:
            try:
                await pubsub.unsubscribe(*channels)
                await pubsub.aclose()
            except Exception:  # noqa: S110
                pass

        await self._set_status("stopped")
        log.info("live.stopped", id=self.live_strategy_id)

    async def stop(self) -> None:
        self._stopped.set()

    # ---- helpers ---------------------------------------------------------

    async def _preload_history(
        self,
        ctx: LiveContext,
        source: str,
        symbols: list[str],
        timeframe: str,
    ) -> None:
        async with self.sm() as session:
            for sym in symbols:
                rows = (
                    await session.execute(
                        text(
                            "SELECT source, symbol, ts, open, high, low, close, volume "
                            "  FROM ohlcv "
                            " WHERE source = :src AND symbol = :sym AND timeframe = :tf "
                            " ORDER BY ts DESC LIMIT :lim",
                        ),
                        {"src": source, "sym": sym, "tf": timeframe, "lim": HISTORY_DEPTH},
                    )
                ).all()
                # rows are newest-first; we want oldest-first in the deque.
                for r in reversed(rows):
                    ctx.history_per_symbol[sym].append(
                        EngineBar(
                            source=r[0],
                            symbol=r[1],
                            ts=r[2],
                            open=float(r[3]),
                            high=float(r[4]),
                            low=float(r[5]),
                            close=float(r[6]),
                            volume=float(r[7]),
                        ),
                    )
                if rows:
                    ctx.last_prices[sym] = float(rows[0][6])

    async def _handle_bar(
        self,
        ctx: LiveContext,
        strategy: Strategy,
        bar: EngineBar,
    ) -> None:
        ctx.last_prices[bar.symbol] = bar.close
        ctx.history_per_symbol[bar.symbol].append(bar)
        # Mark to market on every bar (cheap, only updates non-zero positions).
        await self.broker.update_mark(ctx.account_id, bar.symbol, bar.close)

        ctx.pending_intents.clear()
        ctx.pending_log_entries.clear()
        try:
            strategy.on_bar(bar)
        except Exception as e:
            log.exception("live.on_bar_raised", id=self.live_strategy_id, error=str(e))
            await self._emit_event(
                "on_bar_error",
                {"symbol": bar.symbol, "error": f"{type(e).__name__}: {e}"[:500]},
            )
            return

        # Flush any self.log() entries first so they appear before the
        # corresponding order events in the event log.
        for entry in ctx.pending_log_entries:
            await self._emit_event(
                "log",
                {
                    "symbol": bar.symbol,
                    "message": entry["message"],
                    **(entry.get("fields") or {}),
                },
            )

        # Only emit a bar event when something happened — otherwise the log
        # fills with noise on every tick. If a strategy queued intents this
        # bar OR has an open position, surface it.
        any_position = any(p.qty != 0 for p in ctx.positions.values())
        if ctx.pending_intents or any_position:
            await self._emit_event(
                "on_bar",
                {
                    "symbol": bar.symbol,
                    "ts": bar.ts.isoformat(),
                    "close": bar.close,
                    "intents": len(ctx.pending_intents),
                },
            )

        for intent in ctx.pending_intents:
            last = ctx.last_prices.get(intent.symbol, 0.0)
            await self._emit_event(
                "submit",
                {
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "qty": intent.qty,
                    "notional": intent.notional,
                    "reason": intent.reason,
                },
            )
            result = await self.broker.submit(intent, last)
            await self._emit_event(
                "fill" if result.status == "filled" else "reject",
                {
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "status": result.status,
                    "filled_qty": result.filled_qty,
                    "avg_fill_price": result.avg_fill_price,
                    "pnl": result.pnl,
                    "error": result.error,
                },
            )
            if result.status == "filled":
                signed = result.filled_qty if intent.side == "buy" else -result.filled_qty
                ctx.apply_fill(
                    intent.symbol,
                    signed_qty=signed,
                    fill_price=result.avg_fill_price,
                    pnl=result.pnl,
                )

    async def _persist_equity(self, ctx: LiveContext) -> None:
        equity = ctx.current_equity()
        cash = ctx.cash
        async with self.sm() as session:
            await session.execute(
                text(
                    "INSERT INTO account_equity (account_id, ts, equity, cash) "
                    "VALUES (:acc, now(), :eq, :cash) ON CONFLICT DO NOTHING",
                ),
                {"acc": ctx.account_id, "eq": equity, "cash": cash},
            )
            await session.commit()
