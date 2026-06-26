"""live_events: per-live-strategy append-only event log

The runner appends event rows on every meaningful tick so a user can
inspect what their live strategy is doing without grepping worker logs.

Revision ID: 0014_live_events
Revises: 0013_scanner_prompt
Create Date: 2026-07-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_live_events"
down_revision: str | Sequence[str] | None = "0013_scanner_prompt"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_events",
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
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_live_events_lsid_ts",
        "live_events",
        ["live_strategy_id", sa.text("ts DESC")],
    )


def downgrade() -> None:
    op.drop_table("live_events")
