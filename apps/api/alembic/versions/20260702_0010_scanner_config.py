"""scanner_config: single-row table for scanner cadence + last-run telemetry.

Revision ID: 0010_scanner_config
Revises: 0009_funding
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_scanner_config"
down_revision: str | Sequence[str] | None = "0009_funding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scanner_config",
        sa.Column("id", sa.SmallInteger, primary_key=True),
        sa.Column("interval_minutes", sa.Integer, nullable=False, server_default="30"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(32), nullable=True),
        sa.Column("last_signal_count", sa.Integer, nullable=True),
        sa.Column("last_reason", sa.Text, nullable=True),
        sa.Column("last_call_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("id = 1", name="scanner_config_singleton"),
        sa.CheckConstraint(
            "interval_minutes >= 5 AND interval_minutes <= 1440",
            name="scanner_config_interval_range",
        ),
    )
    op.execute("INSERT INTO scanner_config (id) VALUES (1) ON CONFLICT DO NOTHING;")


def downgrade() -> None:
    op.drop_table("scanner_config")
