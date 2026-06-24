"""Pre-trade risk checks. Called by every broker.submit() before fill.

Layers:
    1. Account kill switch — instant reject.
    2. Account daily loss limit — reject if today's realized PnL drops below
       -starting_capital * daily_loss_limit_pct.
    3. Per-strategy size caps (max_notional_per_symbol, max_position_qty) —
       reject if the resulting position would exceed.

If any check fails, the broker records the order as `status='rejected'` with
the reason so it shows up in /portfolio (audit + debuggability).
"""

from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from .broker.base import OrderIntent

log = structlog.get_logger()


@dataclass(slots=True)
class RiskCheckResult:
    ok: bool
    reason: str | None = None


class RiskEngine:
    """Stateless — every check reads the latest from Postgres."""

    async def check(
        self,
        session_maker: async_sessionmaker,
        intent: OrderIntent,
        last_price: float,
    ) -> RiskCheckResult:
        async with session_maker() as session:
            # 1) Account state
            row = (
                await session.execute(
                    text(
                        "SELECT killed, daily_loss_limit_pct, starting_capital "
                        "  FROM accounts WHERE id = :id",
                    ),
                    {"id": intent.account_id},
                )
            ).first()
            if row is None:
                return RiskCheckResult(False, "account not found")
            killed, dll_pct, starting_capital = row
            if killed:
                return RiskCheckResult(False, "account killed")

            # 2) Daily loss limit
            if dll_pct is not None:
                pnl_today = (
                    await session.execute(
                        text(
                            "SELECT COALESCE(SUM(pnl), 0) "
                            "  FROM fills "
                            " WHERE account_id = :id AND ts >= CURRENT_DATE",
                        ),
                        {"id": intent.account_id},
                    )
                ).scalar_one()
                limit = -(float(starting_capital) * float(dll_pct))
                pnl_f = float(pnl_today)
                if pnl_f < limit:
                    return RiskCheckResult(
                        False,
                        f"daily loss limit breached (pnl={pnl_f:.2f} < {limit:.2f})",
                    )

            # 3) Per-strategy size caps
            if intent.live_strategy_id is None:
                return RiskCheckResult(True)
            caps = (
                await session.execute(
                    text(
                        "SELECT max_notional_per_symbol, max_position_qty "
                        "  FROM live_strategies WHERE id = :id",
                    ),
                    {"id": intent.live_strategy_id},
                )
            ).first()
            if caps is None:
                return RiskCheckResult(True)
            max_notional, max_qty = caps
            if max_notional is None and max_qty is None:
                return RiskCheckResult(True)

            # Compute would-be new position
            cur_row = (
                await session.execute(
                    text(
                        "SELECT qty FROM positions  WHERE account_id = :a AND symbol = :s",
                    ),
                    {"a": intent.account_id, "s": intent.symbol},
                )
            ).first()
            cur_qty = float(cur_row[0]) if cur_row else 0.0

            qty = intent.qty
            if qty is None and intent.notional is not None and last_price > 0:
                qty = float(intent.notional) / float(last_price)
            if qty is None or qty <= 0:
                return RiskCheckResult(False, "invalid qty/price")
            signed = qty if intent.side == "buy" else -qty
            new_qty = cur_qty + signed

            if max_qty is not None and abs(new_qty) > float(max_qty):
                return RiskCheckResult(
                    False,
                    f"would exceed max_position_qty ({abs(new_qty):.6f} > {float(max_qty)})",
                )
            if max_notional is not None:
                new_notional = abs(new_qty) * float(last_price)
                if new_notional > float(max_notional):
                    return RiskCheckResult(
                        False,
                        f"would exceed max_notional_per_symbol "
                        f"({new_notional:.2f} > {float(max_notional):.2f})",
                    )

        return RiskCheckResult(True)
