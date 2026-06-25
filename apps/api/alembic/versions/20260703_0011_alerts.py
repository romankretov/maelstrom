"""alerts: user-defined price / funding / change conditions

Revision ID: 0011_alerts
Revises: 0010_scanner_config
Create Date: 2026-07-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.dialects import postgresql

revision: str = "0011_alerts"
down_revision: str | Sequence[str] | None = "0010_scanner_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            GUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        # condition: price_above | price_below | change_24h_above | change_24h_below
        # | funding_above | funding_below
        sa.Column("condition", sa.String(32), nullable=False),
        sa.Column("threshold", sa.Numeric(20, 10), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "cooldown_minutes",
            sa.Integer,
            nullable=False,
            server_default="60",
        ),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_value", sa.Numeric(20, 10), nullable=True),
        sa.Column("trigger_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_alerts_user", "alerts", ["user_id"])
    op.create_index(
        "ix_alerts_enabled",
        "alerts",
        ["enabled"],
        postgresql_where=sa.text("enabled = TRUE"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
