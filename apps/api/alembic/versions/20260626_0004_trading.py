"""trading: accounts, live_strategies, orders, fills, positions, account_equity

Revision ID: 0004_trading
Revises: 0003_strategies
Create Date: 2026-06-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy.dialects import postgresql

revision: str = "0004_trading"
down_revision: str | Sequence[str] | None = "0003_strategies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ accounts
    op.create_table(
        "accounts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column(
            "kind",
            sa.String(32),
            nullable=False,
        ),  # paper | live_hl_testnet | live_hl_main
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("starting_capital", sa.Numeric(20, 4), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("api_key_enc", sa.LargeBinary, nullable=True),
        sa.Column("api_secret_enc", sa.LargeBinary, nullable=True),
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
    op.create_index("ix_accounts_owner", "accounts", ["owner_id"])
    op.create_index("ix_accounts_kind", "accounts", ["kind"])

    # ------------------------------------------------------------------ live_strategies
    op.create_table(
        "live_strategies",
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
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbols", postgresql.ARRAY(sa.String(64)), nullable=False),
        sa.Column("timeframe", sa.String(8), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        # paused | pending_start | running | pending_stop | stopped | failed
        sa.Column("status", sa.String(20), nullable=False, server_default="paused"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requester_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
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
    op.create_index("ix_live_strategies_account", "live_strategies", ["account_id"])
    op.create_index("ix_live_strategies_status", "live_strategies", ["status"])

    # ------------------------------------------------------------------ orders
    op.create_table(
        "orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "live_strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("live_strategies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),  # buy | sell
        sa.Column("qty", sa.Numeric(28, 10), nullable=False),
        sa.Column("price", sa.Numeric(20, 10), nullable=True),  # NULL for market
        sa.Column("order_type", sa.String(16), nullable=False, server_default="market"),
        # pending | submitted | filled | partial | cancelled | rejected
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("filled_qty", sa.Numeric(28, 10), nullable=False, server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(20, 10), nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=True, unique=True),
        sa.Column("exchange_order_id", sa.String(160), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_orders_account", "orders", ["account_id"])
    op.create_index("ix_orders_strategy", "orders", ["live_strategy_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index(
        "ix_orders_created",
        "orders",
        [sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------ fills
    op.create_table(
        "fills",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Numeric(28, 10), nullable=False),
        sa.Column("price", sa.Numeric(20, 10), nullable=False),
        sa.Column("fee", sa.Numeric(20, 10), nullable=False, server_default="0"),
        sa.Column("pnl", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exchange_fill_id", sa.String(160), nullable=True),
    )
    op.create_index("ix_fills_account", "fills", ["account_id", sa.text("ts DESC")])
    op.create_index("ix_fills_order", "fills", ["order_id"])

    # ------------------------------------------------------------------ positions
    op.create_table(
        "positions",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("qty", sa.Numeric(28, 10), nullable=False, server_default="0"),
        sa.Column("avg_price", sa.Numeric(20, 10), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("last_price", sa.Numeric(20, 10), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("account_id", "symbol", name="pk_positions"),
    )

    # ------------------------------------------------------------------ account_equity (TimescaleDB hypertable)
    op.create_table(
        "account_equity",
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Numeric(20, 4), nullable=False),
        sa.Column("cash", sa.Numeric(20, 4), nullable=False),
        sa.PrimaryKeyConstraint("account_id", "ts", name="pk_account_equity"),
    )
    op.execute(
        "SELECT create_hypertable('account_equity', 'ts', "
        "chunk_time_interval => INTERVAL '30 days', if_not_exists => TRUE);"
    )


def downgrade() -> None:
    op.drop_table("account_equity")
    op.drop_table("positions")
    op.drop_table("fills")
    op.drop_table("orders")
    op.drop_table("live_strategies")
    op.drop_table("accounts")
