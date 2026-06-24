"""risk: kill switch + account daily loss limit + per-strategy size caps

Revision ID: 0005_risk
Revises: 0004_trading
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_risk"
down_revision: str | Sequence[str] | None = "0004_trading"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("killed", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    # daily_loss_limit_pct: e.g. 0.05 means halt new orders if today's realized
    # PnL drops below -5% of starting_capital. NULL = no limit.
    op.add_column(
        "accounts",
        sa.Column("daily_loss_limit_pct", sa.Numeric(6, 4), nullable=True),
    )

    op.add_column(
        "live_strategies",
        sa.Column("max_notional_per_symbol", sa.Numeric(20, 4), nullable=True),
    )
    op.add_column(
        "live_strategies",
        sa.Column("max_position_qty", sa.Numeric(28, 10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("live_strategies", "max_position_qty")
    op.drop_column("live_strategies", "max_notional_per_symbol")
    op.drop_column("accounts", "daily_loss_limit_pct")
    op.drop_column("accounts", "killed")
