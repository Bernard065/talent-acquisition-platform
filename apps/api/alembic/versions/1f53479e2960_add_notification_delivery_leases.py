"""add notification delivery leases

Revision ID: 1f53479e2960
Revises: 3bc6e17df7b3
Create Date: 2026-09-10 10:45:31.023429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f53479e2960'
down_revision: Union[str, Sequence[str], None] = '3bc6e17df7b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "notifications",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "notifications",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("locked_by", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_notifications_status_next_attempt_at",
        "notifications",
        ["status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_notifications_status_next_attempt_at",
        table_name="notifications",
    )
    op.drop_column("notifications", "locked_by")
    op.drop_column("notifications", "locked_at")
    op.drop_column("notifications", "next_attempt_at")
