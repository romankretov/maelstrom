"""PaperBroker — fills immediately at last_price * (1 ± slippage), persists to
orders/fills/positions tables. Same accounting math as BacktestEngine.

Atomicity: each submit() runs INSERT order + INSERT fill + UPSERT position
in one transaction; on any error we roll back and the order ends up in
status='rejected' with the error stored.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from maelstrom_worker.risk import RiskEngine

from .base import Broker, OrderIntent, OrderResult

log = structlog.get_logger()


# Default fee + slippage. Configurable later via account.meta if useful.
DEFAULT_FEE_RATE = 0.0005  # 5 bps round-trip half (10 bps total)
DEFAULT_SLIPPAGE = 0.0002  # 2 bps adverse from last close


_REJECT_SQL = text(
    """
    INSERT INTO orders
      (account_id, live_strategy_id, source, symbol, side, qty, order_type,
       status, error, reason, idempotency_key, completed_at)
    VALUES
      (:account_id, :live_strategy_id, :source, :symbol, :side, :qty, :order_type,
       'rejected', :err, :reason, :idempotency_key, now())
    RETURNING id
    """,
)


_INSERT_ORDER_SQL = text(
    """
    INSERT INTO orders
      (account_id, live_strategy_id, source, symbol, side, qty, order_type,
       status, filled_qty, avg_fill_price, reason, idempotency_key,
       submitted_at, completed_at)
    VALUES
      (:account_id, :live_strategy_id, :source, :symbol, :side, :qty, :order_type,
       'filled', :qty, :price, :reason, :idempotency_key,
       now(), now())
    RETURNING id
    """,
)


_INSERT_FILL_SQL = text(
    """
    INSERT INTO fills
      (order_id, account_id, symbol, side, qty, price, fee, pnl, ts)
    VALUES
      (:order_id, :account_id, :symbol, :side, :qty, :price, :fee, :pnl, :ts)
    """,
)


_UPSERT_POSITION_SQL = text(
    """
    INSERT INTO positions
      (account_id, symbol, qty, avg_price, realized_pnl, last_price, updated_at)
    VALUES
      (:account_id, :symbol, :qty, :avg_price, :realized_pnl, :last_price, now())
    ON CONFLICT (account_id, symbol) DO UPDATE SET
        qty          = EXCLUDED.qty,
        avg_price    = EXCLUDED.avg_price,
        realized_pnl = positions.realized_pnl + EXCLUDED.realized_pnl,
        last_price   = EXCLUDED.last_price,
        updated_at   = now()
    """,
)


_MARK_SQL = text(
    """
    UPDATE positions
       SET last_price = :price,
           updated_at = now()
     WHERE account_id = :account_id
       AND symbol = :symbol
       AND qty != 0
    """,
)


_GET_POSITION_SQL = text(
    """
    SELECT qty, avg_price
      FROM positions
     WHERE account_id = :account_id
       AND symbol = :symbol
    """,
)


class PaperBroker(Broker):
    def __init__(
        self,
        session_maker: async_sessionmaker,
        fee_rate: float = DEFAULT_FEE_RATE,
        risk_engine: RiskEngine | None = None,
    ) -> None:
        self.sm = session_maker
        self.fee_rate = fee_rate
        self.risk = risk_engine or RiskEngine()

    async def submit(self, intent: OrderIntent, last_price: float) -> OrderResult:
        ts = datetime.now(UTC)

        # Pre-trade risk: reject before doing anything else if the account is
        # killed / over its daily loss / over per-strategy size cap.
        risk = await self.risk.check(self.sm, intent, last_price)
        if not risk.ok:
            return await self._reject(intent, risk.reason or "risk rejected", ts)

        # Resolve qty (intent may use notional)
        qty = intent.qty
        if qty is None and intent.notional is not None and last_price > 0:
            qty = float(intent.notional) / float(last_price)
        if qty is None or qty <= 0 or last_price <= 0:
            return await self._reject(intent, "invalid qty/price", ts)

        # Simulated fill: last_price ± slippage in the adverse direction.
        slip = last_price * DEFAULT_SLIPPAGE
        fill_price = last_price + slip if intent.side == "buy" else last_price - slip
        signed = qty if intent.side == "buy" else -qty
        fee = abs(signed) * fill_price * self.fee_rate

        async with self.sm() as session:
            # Read current position for PnL math.
            row = (
                await session.execute(
                    _GET_POSITION_SQL,
                    {"account_id": intent.account_id, "symbol": intent.symbol},
                )
            ).first()
            old_qty = float(row[0]) if row else 0.0
            old_avg = float(row[1]) if row else 0.0
            new_qty = old_qty + signed

            # Realized PnL on closing portion.
            pnl = 0.0
            if (old_qty > 0 > signed) or (old_qty < 0 < signed):
                closing_qty = min(abs(signed), abs(old_qty))
                if old_qty > 0:
                    pnl = (fill_price - old_avg) * closing_qty
                else:
                    pnl = (old_avg - fill_price) * closing_qty

            # New average price: only changes when same-direction size grows.
            if new_qty == 0:
                new_avg = 0.0
            elif (old_qty >= 0 and new_qty > old_qty) or (old_qty <= 0 and new_qty < old_qty):
                new_avg = (old_avg * old_qty + fill_price * signed) / new_qty
            else:
                new_avg = old_avg

            order_id = (
                await session.execute(
                    _INSERT_ORDER_SQL,
                    {
                        "account_id": intent.account_id,
                        "live_strategy_id": intent.live_strategy_id,
                        "source": intent.source,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": qty,
                        "price": fill_price,
                        "order_type": intent.order_type,
                        "reason": intent.reason,
                        "idempotency_key": intent.idempotency_key,
                    },
                )
            ).scalar_one()

            await session.execute(
                _INSERT_FILL_SQL,
                {
                    "order_id": order_id,
                    "account_id": intent.account_id,
                    "symbol": intent.symbol,
                    "side": intent.side,
                    "qty": qty,
                    "price": fill_price,
                    "fee": fee,
                    "pnl": pnl,
                    "ts": ts,
                },
            )

            await session.execute(
                _UPSERT_POSITION_SQL,
                {
                    "account_id": intent.account_id,
                    "symbol": intent.symbol,
                    "qty": new_qty,
                    "avg_price": new_avg,
                    "realized_pnl": pnl,  # incremented in ON CONFLICT branch
                    "last_price": fill_price,
                },
            )
            await session.commit()

        log.info(
            "paper.fill",
            symbol=intent.symbol,
            side=intent.side,
            qty=qty,
            price=fill_price,
            pnl=pnl,
        )
        return OrderResult(
            order_id=str(order_id),
            status="filled",
            filled_qty=qty,
            avg_fill_price=fill_price,
            fee=fee,
            pnl=pnl,
            ts=ts,
        )

    async def update_mark(self, account_id: str, symbol: str, last_price: float) -> None:
        async with self.sm() as session:
            await session.execute(
                _MARK_SQL,
                {"account_id": account_id, "symbol": symbol, "price": last_price},
            )
            await session.commit()

    async def _reject(self, intent: OrderIntent, error: str, ts: datetime) -> OrderResult:
        async with self.sm() as session:
            row = (
                await session.execute(
                    _REJECT_SQL,
                    {
                        "account_id": intent.account_id,
                        "live_strategy_id": intent.live_strategy_id,
                        "source": intent.source,
                        "symbol": intent.symbol,
                        "side": intent.side,
                        "qty": intent.qty or 0,
                        "order_type": intent.order_type,
                        "err": error,
                        "reason": intent.reason,
                        "idempotency_key": intent.idempotency_key,
                    },
                )
            ).scalar_one()
            await session.commit()
        log.warning("paper.reject", symbol=intent.symbol, side=intent.side, error=error)
        return OrderResult(
            order_id=str(row),
            status="rejected",
            filled_qty=0.0,
            avg_fill_price=0.0,
            fee=0.0,
            pnl=0.0,
            ts=ts,
            error=error,
        )
