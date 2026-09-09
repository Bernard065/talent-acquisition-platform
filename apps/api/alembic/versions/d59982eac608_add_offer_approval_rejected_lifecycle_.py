"""add offer approval rejected lifecycle event

Revision ID: d59982eac608
Revises: 4b4936fa6a71
Create Date: 2026-09-09 14:12:24.571171

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd59982eac608'
down_revision: Union[str, Sequence[str], None] = '4b4936fa6a71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE offer_lifecycle_event_type "
        "ADD VALUE IF NOT EXISTS 'approval_rejected'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL does not safely support removing enum values in place.
    pass
