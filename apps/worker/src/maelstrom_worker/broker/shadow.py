"""ShadowBroker — accepts the same interface as PaperBroker / HyperliquidBroker
but never touches the real `fills`, `orders`, or `positions` tables.

Instead it records every would-be fill into `shadow_fills`, keyed by the
live_strategy_id, so the user can inspect what the strategy would have
done against the live stream without putting capital at risk.

Position math is simulated in-memory per (live_strategy_id, symbol) so
realized-PnL on closes is still meaningful. No risk-engine: the whole
point of shadow mode is to see uninhibited behavior.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .base import Broker, OrderIntent, OrderResult

log = structlog.get_logger()


_INSERT_SHADOW_FILL_SQL = text(
    """
    INSERT INTO shadow_fills
        (live_strategy_id, ts, symbol, side, qty, price, notional, fee, pnl, reason)
    VALUES
        (:lsid, :ts, :symbol, :side, :qty, :price, :notional, :fee, :pnl, :reason)
    RETURNING id
    """,
)


DEFAULT_FEE_RATE = 0.0005
DEFAULT_SLIPPAGE = 0.0002


@dataclass(slots=True)
class _Pos:
    qty: float = 0.0
    avg: float = 0.0


class ShadowBroker(Broker):
    """One instance per LiveRunner (manager spawns it per live_strategy_id)."""

    def __init__(
        self,
        session_maker: async_sessionmaker,
        live_strategy_id: str,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> None:
        self.sm = session_maker
        self.live_strategy_id = live_strategy_id
        self.fee_rate = fee_rate
        # In-memory positions — process-local, lost on worker restart. That's
        # acceptable for shadow mode; user can scroll the fills table to
        # reconstruct if they really need.
        self._pos: dict[str, _Pos] = {}

    async def submit(self, intent: OrderIntent, last_price: float) -> OrderResult:
        ts = datetime.now(UTC)
        qty = intent.qty
        if qty is None and intent.notional is not None and last_price > 0:
            qty = float(intent.notional) / float(last_price)
        if qty is None or qty <= 0 or last_price <= 0:
            return OrderResult(
                order_id="shadow-reject",
                status="rejected",
                filled_qty=0.0,
                avg_fill_price=0.0,
                fee=0.0,
                pnl=0.0,
                ts=ts,
                error="invalid qty/price",
            )

        slip = last_price * DEFAULT_SLIPPAGE
        fill_price = last_price + slip if intent.side == "buy" else last_price - slip
        signed = qty if intent.side == "buy" else -qty
        fee = abs(signed) * fill_price * self.fee_rate

        pos = self._pos.setdefault(intent.symbol, _Pos())
        old_qty = pos.qty
        old_avg = pos.avg
        new_qty = old_qty + signed

        pnl = 0.0
        if (old_qty > 0 > signed) or (old_qty < 0 < signed):
            closing = min(abs(signed), abs(old_qty))
            if old_qty > 0:
                pnl = (fill_price - old_avg) * closing
            else:
                pnl = (old_avg - fill_price) * closing

        if new_qty == 0:
            new_avg = 0.0
        elif (old_qty >= 0 and new_qty > old_qty) or (old_qty <= 0 and new_qty < old_qty):
            new_avg = (old_avg * old_qty + fill_price * signed) / new_qty
        else:
            new_avg = old_avg
        pos.qty = new_qty
        pos.avg = new_avg

        async with self.sm() as session:
            fill_id = (
                await session.execute(
                    _INSERT_SHADOW_FILL_SQL,
                    {
                        "lsid": self.live_strategy_id,
                        "ts": ts,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": qty,
                        "price": fill_price,
                        "notional": qty * fill_price,
                        "fee": fee,
                        "pnl": pnl,
                        "reason": intent.reason,
                    },
                )
            ).scalar_one()
            await session.commit()

        log.info(
            "shadow.fill",
            live_strategy_id=self.live_strategy_id,
            symbol=intent.symbol,
            side=intent.side,
            qty=qty,
            price=fill_price,
            pnl=pnl,
        )

        return OrderResult(
            order_id=f"shadow-{fill_id}",
            status="filled",
            filled_qty=qty,
            avg_fill_price=fill_price,
            fee=fee,
            pnl=pnl,
            ts=ts,
        )

    async def update_mark(self, account_id: str, symbol: str, last_price: float) -> None:
        # Shadow mode has no positions table to update — marks are implicit
        # in subsequent fills' fill_price math.
        return
