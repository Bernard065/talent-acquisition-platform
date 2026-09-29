"""Track the first notification provider attempt for idempotency recovery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e5b89152b00"
down_revision: str | Sequence[str] | None = "e7f8c9a2d314"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist first provider-attempt time and index bounded expiry scans."""
    op.add_column(
        "notifications",
        sa.Column("first_delivery_attempt_at", sa.DateTime(timezone=True)),
    )
    # Existing attempts predate this marker. created_at is conservative: it is
    # never later than a provider request and therefore cannot extend the safe
    # provider-idempotency retry window during deployment recovery.
    op.execute(
        sa.text(
            "UPDATE notifications SET first_delivery_attempt_at = created_at WHERE attempts > 0"
        )
    )
    op.create_index(
        "ix_notifications_status_first_delivery_attempt_at",
        "notifications",
        ["status", "first_delivery_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the provider-attempt marker and its lookup index."""
    op.drop_index(
        "ix_notifications_status_first_delivery_attempt_at",
        table_name="notifications",
    )
    op.drop_column("notifications", "first_delivery_attempt_at")
