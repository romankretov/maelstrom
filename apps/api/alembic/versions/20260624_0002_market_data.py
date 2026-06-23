"""market data: instruments + ohlcv hypertable + trades hypertable + backfill_jobs

Revision ID: 0002_market_data
Revises: 0001_initial
Create Date: 2026-06-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_market_data"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ instruments
    op.create_table(
        "instruments",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("symbol", sa.String(64), primary_key=True),
        sa.Column("raw_symbol", sa.String(96), nullable=False),
        sa.Column("base", sa.String(32), nullable=False),
        sa.Column("quote", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),  # 'perp' | 'spot' | 'equity'
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "meta",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_instruments_active", "instruments", ["active"])
    op.create_index("ix_instruments_kind", "instruments", ["kind"])
    op.create_index(
        "ix_instruments_base_quote",
        "instruments",
        ["base", "quote"],
    )

    # ------------------------------------------------------------------ ohlcv (hypertable)
    op.create_table(
        "ohlcv",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Float, nullable=False),
        sa.Column("high", sa.Float, nullable=False),
        sa.Column("low", sa.Float, nullable=False),
        sa.Column("close", sa.Float, nullable=False),
        sa.Column("volume", sa.Float, nullable=False),
        sa.Column("trades_count", sa.Integer, nullable=True),
        sa.PrimaryKeyConstraint("source", "symbol", "timeframe", "ts", name="pk_ohlcv"),
    )
    op.execute(
        "SELECT create_hypertable('ohlcv', 'ts', "
        "chunk_time_interval => INTERVAL '7 days', if_not_exists => TRUE);"
    )
    op.create_index(
        "ix_ohlcv_lookup",
        "ohlcv",
        ["source", "symbol", "timeframe", sa.text("ts DESC")],
    )

    # ------------------------------------------------------------------ trades (hypertable)
    op.create_table(
        "trades",
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_id", sa.String(96), nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("qty", sa.Float, nullable=False),
        sa.Column("side", sa.String(4), nullable=False),  # 'buy' | 'sell'
        sa.PrimaryKeyConstraint("source", "symbol", "ts", "trade_id", name="pk_trades"),
    )
    op.execute(
        "SELECT create_hypertable('trades', 'ts', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.create_index(
        "ix_trades_lookup",
        "trades",
        ["source", "symbol", sa.text("ts DESC")],
    )

    # ------------------------------------------------------------------ backfill_jobs
    op.create_table(
        "backfill_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),  # pending | running | done | failed
        sa.Column("bars_written", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_backfill_status", "backfill_jobs", ["status"])
    op.create_index(
        "ix_backfill_lookup",
        "backfill_jobs",
        ["source", "symbol", "timeframe"],
    )


def downgrade() -> None:
    op.drop_table("backfill_jobs")
    op.drop_table("trades")
    op.drop_table("ohlcv")
    op.drop_table("instruments")
