"""strategies + versions + backtest tables

Revision ID: 0003_strategies
Revises: 0002_market_data
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.dialects import postgresql

revision: str = "0003_strategies"
down_revision: str | Sequence[str] | None = "0002_market_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ strategies
    op.create_table(
        "strategies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
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
    op.create_index("ix_strategies_owner", "strategies", ["owner_id"])
    op.create_index("ix_strategies_archived", "strategies", ["is_archived"])

    # ------------------------------------------------------------------ strategy_versions
    op.create_table(
        "strategy_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("code", sa.Text, nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("author_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("strategy_id", "version", name="uq_strategy_version"),
    )
    op.create_index("ix_strategy_versions_strategy", "strategy_versions", ["strategy_id"])

    # ------------------------------------------------------------------ backtest_runs
    op.create_table(
        "backtest_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "symbols",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
        ),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("initial_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("requester_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_backtest_runs_strategy", "backtest_runs", ["strategy_id"])
    op.create_index("ix_backtest_runs_status", "backtest_runs", ["status"])
    op.create_index(
        "ix_backtest_runs_created",
        "backtest_runs",
        [sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------ backtest_trades
    op.create_table(
        "backtest_trades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("fee", sa.Float, nullable=False, server_default="0"),
        sa.Column("pnl", sa.Float, nullable=False, server_default="0"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
    )
    op.create_index("ix_backtest_trades_run", "backtest_trades", ["run_id", "ts"])

    # ------------------------------------------------------------------ backtest_equity
    op.create_table(
        "backtest_equity",
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("backtest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Float, nullable=False),
        sa.Column("drawdown", sa.Float, nullable=False),
        sa.PrimaryKeyConstraint("run_id", "ts", name="pk_backtest_equity"),
    )


def downgrade() -> None:
    op.drop_table("backtest_equity")
    op.drop_table("backtest_trades")
    op.drop_table("backtest_runs")
    op.drop_table("strategy_versions")
    op.drop_table("strategies")
