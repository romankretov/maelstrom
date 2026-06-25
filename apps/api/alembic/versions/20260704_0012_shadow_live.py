"""shadow_live mode: live_strategies.shadow_mode + shadow_fills table

Shadow-live runs subscribe to the live bar stream but route would-be
orders to shadow_fills instead of the broker. Lets users validate a
strategy on real market microstructure (gap fills, ws latency, etc.)
without capital risk — a step between paper backtest and real live.

Revision ID: 0012_shadow_live
Revises: 0011_alerts
Create Date: 2026-07-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_shadow_live"
down_revision: str | Sequence[str] | None = "0011_alerts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "live_strategies",
        sa.Column(
            "shadow_mode",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "shadow_fills",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "live_strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Numeric(28, 12), nullable=False),
        sa.Column("price", sa.Numeric(28, 12), nullable=False),
        sa.Column("notional", sa.Numeric(28, 12), nullable=False),
        sa.Column("fee", sa.Numeric(28, 12), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Numeric(28, 12), nullable=False, server_default="0"),
        sa.Column("reason", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_shadow_fills_live_strategy_ts",
        "shadow_fills",
        ["live_strategy_id", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_table("shadow_fills")
    op.drop_column("live_strategies", "shadow_mode")
