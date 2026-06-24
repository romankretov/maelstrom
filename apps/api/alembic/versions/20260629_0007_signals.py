"""signals: LLM-generated trade ideas

Revision ID: 0007_signals
Revises: 0006_llm
Create Date: 2026-06-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_signals"
down_revision: str | Sequence[str] | None = "0006_llm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("scanner", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("score", sa.Numeric(6, 2), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 2), nullable=True),
        sa.Column("horizon", sa.String(16), nullable=True),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "llm_call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_calls.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_signals_ts", "signals", [sa.text("ts DESC")])
    op.create_index("ix_signals_symbol", "signals", ["symbol"])
    op.create_index("ix_signals_scanner", "signals", ["scanner"])


def downgrade() -> None:
    op.drop_table("signals")
