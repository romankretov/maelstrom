"""funding_rates: per-perp historical funding rates (TimescaleDB hypertable).

Revision ID: 0009_funding
Revises: 0008_notifications
Create Date: 2026-07-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_funding"
down_revision: str | Sequence[str] | None = "0008_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "funding_rates",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.PrimaryKeyConstraint("source", "symbol", "ts", name="pk_funding_rates"),
    )
    op.create_index(
        "ix_funding_rates_source_symbol_ts",
        "funding_rates",
        ["source", "symbol", "ts"],
    )
    op.execute(
        "SELECT create_hypertable('funding_rates', 'ts', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE, "
        "migrate_data => TRUE);",
    )


def downgrade() -> None:
    op.drop_index("ix_funding_rates_source_symbol_ts", table_name="funding_rates")
    op.drop_table("funding_rates")
