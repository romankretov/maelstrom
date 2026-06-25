"""scanner_config.system_prompt: editable scanner steering

Revision ID: 0013_scanner_prompt
Revises: 0012_shadow_live
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_scanner_prompt"
down_revision: str | Sequence[str] | None = "0012_shadow_live"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scanner_config",
        sa.Column("system_prompt", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scanner_config", "system_prompt")
