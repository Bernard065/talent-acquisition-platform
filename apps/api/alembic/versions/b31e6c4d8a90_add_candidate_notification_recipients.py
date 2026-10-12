"""allow interview notifications to target candidate profiles

Revision ID: b31e6c4d8a90
Revises: a91c7e2d4f60, c5d9a18e2f60
Create Date: 2026-10-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b31e6c4d8a90"
down_revision: str | Sequence[str] | None = (
    "a91c7e2d4f60",
    "c5d9a18e2f60",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support durable email delivery to candidates without user accounts."""
    op.alter_column(
        "notifications",
        "recipient_user_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.add_column(
        "notifications",
        sa.Column("recipient_candidate_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "notifications",
        sa.Column("event_version", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_notifications_recipient_candidate_id_candidates",
        "notifications",
        "candidates",
        ["recipient_candidate_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_notifications_exactly_one_recipient",
        "notifications",
        "(recipient_user_id IS NOT NULL AND recipient_candidate_id IS NULL) OR "
        "(recipient_user_id IS NULL AND recipient_candidate_id IS NOT NULL)",
    )
    op.create_unique_constraint(
        "uq_notifications_tenant_candidate_event_deduplication",
        "notifications",
        [
            "tenant_id",
            "recipient_candidate_id",
            "channel",
            "event_type",
            "deduplication_key",
        ],
    )
    op.create_index(
        "ix_notifications_recipient_candidate_status",
        "notifications",
        ["recipient_candidate_id", "status"],
    )


def downgrade() -> None:
    """Remove candidate recipients from notification intents."""
    op.execute(
        sa.text(
            "DELETE FROM notifications WHERE recipient_candidate_id IS NOT NULL"
        )
    )
    op.drop_index(
        "ix_notifications_recipient_candidate_status",
        table_name="notifications",
    )
    op.drop_constraint(
        "uq_notifications_tenant_candidate_event_deduplication",
        "notifications",
        type_="unique",
    )
    op.drop_constraint(
        "ck_notifications_exactly_one_recipient",
        "notifications",
        type_="check",
    )
    op.drop_constraint(
        "fk_notifications_recipient_candidate_id_candidates",
        "notifications",
        type_="foreignkey",
    )
    op.drop_column("notifications", "recipient_candidate_id")
    op.drop_column("notifications", "event_version")
    op.alter_column(
        "notifications",
        "recipient_user_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
