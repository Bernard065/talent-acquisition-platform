"""add offer expiry timestamp

Revision ID: 634be0d89f10
Revises: d59982eac608
Create Date: 2026-09-09 21:18:25.062780

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "634be0d89f10"
down_revision: Union[str, Sequence[str], None] = "d59982eac608"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "offers",
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_offers_expired_at_required",
        "offers",
        "(status != 'expired') OR expired_at IS NOT NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "ck_offers_expired_at_required",
        "offers",
        type_="check",
    )
    op.drop_column("offers", "expired_at")
