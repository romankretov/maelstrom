"""strategies.notes: per-strategy markdown notes

Revision ID: 0016_strategy_notes
Revises: 0015_watchlist
Create Date: 2026-07-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_strategy_notes"
down_revision: str | Sequence[str] | None = "0015_watchlist"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("strategies", "notes")
