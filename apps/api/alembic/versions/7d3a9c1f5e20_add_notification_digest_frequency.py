"""Add daily or weekly frequency to notification preferences.

Revision ID: 7d3a9c1f5e20
Revises: 2c7a91e4d630
Create Date: 2026-10-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d3a9c1f5e20"
down_revision: str | Sequence[str] | None = "2c7a91e4d630"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store a validated delivery cadence, defaulting existing preferences to daily."""
    op.add_column(
        "notification_preferences",
        sa.Column(
            "digest_frequency",
            sa.String(length=10),
            server_default="daily",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_notification_preferences_digest_frequency",
        "notification_preferences",
        "digest_frequency in ('daily', 'weekly')",
    )


def downgrade() -> None:
    """Remove the notification digest cadence preference."""
    op.drop_constraint(
        "ck_notification_preferences_digest_frequency",
        "notification_preferences",
        type_="check",
    )
    op.drop_column("notification_preferences", "digest_frequency")
