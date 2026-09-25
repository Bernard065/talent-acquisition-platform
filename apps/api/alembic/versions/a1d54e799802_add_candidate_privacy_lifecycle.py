"""add candidate privacy lifecycle fields

Revision ID: a1d54e799802
Revises: ce40e9bb687d
Create Date: 2026-09-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1d54e799802"
down_revision: str | Sequence[str] | None = "ce40e9bb687d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add candidate erasure tracking without changing existing records."""
    privacy_status = sa.Enum(
        "active",
        "erasure_pending",
        "erased",
        name="candidate_privacy_status",
    )
    privacy_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "candidates",
        sa.Column(
            "privacy_status",
            privacy_status,
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column(
        "candidates",
        sa.Column("erasure_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidates",
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_documents",
        sa.Column(
            "upload_authorization_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_candidates_privacy_lifecycle_timestamps_consistent",
        "candidates",
        "(privacy_status = 'active' AND erasure_requested_at IS NULL "
        "AND erased_at IS NULL) OR "
        "(privacy_status = 'erasure_pending' AND erasure_requested_at IS NOT NULL "
        "AND erased_at IS NULL) OR "
        "(privacy_status = 'erased' AND erasure_requested_at IS NOT NULL "
        "AND erased_at IS NOT NULL)",
    )
    op.create_index(
        "ix_candidates_tenant_privacy_status_created_at",
        "candidates",
        ["tenant_id", "privacy_status", "created_at"],
    )


def downgrade() -> None:
    """Remove candidate erasure tracking."""
    op.drop_index(
        "ix_candidates_tenant_privacy_status_created_at",
        table_name="candidates",
    )
    op.drop_constraint(
        "ck_candidates_privacy_lifecycle_timestamps_consistent",
        "candidates",
        type_="check",
    )
    op.drop_column("candidate_documents", "upload_authorization_expires_at")
    op.drop_column("candidates", "erased_at")
    op.drop_column("candidates", "erasure_requested_at")
    op.drop_column("candidates", "privacy_status")
    sa.Enum(name="candidate_privacy_status").drop(op.get_bind(), checkfirst=True)
