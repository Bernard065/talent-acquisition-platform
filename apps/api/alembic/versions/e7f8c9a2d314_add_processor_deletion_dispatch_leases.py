"""Add durable claim, retry, and lease metadata for processor deletions.

Revision ID: e7f8c9a2d314
Revises: c4e9a7216d02
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8c9a2d314"
down_revision: str | Sequence[str] | None = "c4e9a7216d02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist leases and backoff state for processor deletion dispatch."""
    op.add_column(
        "candidate_processor_deletion_requests",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "candidate_processor_deletion_requests",
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "candidate_processor_deletion_requests",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_processor_deletion_requests",
        sa.Column("locked_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "candidate_processor_deletion_requests",
        sa.Column("last_failure_code", sa.String(length=100), nullable=True),
    )

    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_status"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_status"),
        "candidate_processor_deletion_requests",
        "status IN ('pending', 'processing', 'completed', 'exception', 'waived')",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_attempt_count_nonneg"),
        "candidate_processor_deletion_requests",
        "attempt_count >= 0",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_lease_state"),
        "candidate_processor_deletion_requests",
        "(status = 'processing' AND locked_at IS NOT NULL AND locked_by IS NOT NULL) "
        "OR (status != 'processing' AND locked_at IS NULL AND locked_by IS NULL)",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_status_metadata"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_status_metadata"),
        "candidate_processor_deletion_requests",
        "(status IN ('pending', 'processing') AND status_changed_at IS NULL "
        "AND status_changed_by_subject IS NULL AND resolution_code IS NULL) "
        "OR (status = 'completed' AND status_changed_at IS NOT NULL "
        "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NULL) "
        "OR (status IN ('exception', 'waived') AND status_changed_at IS NOT NULL "
        "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NOT NULL)",
    )
    op.create_index(
        "ix_candidate_processor_deletion_requests_dispatch",
        "candidate_processor_deletion_requests",
        ["status", "next_attempt_at", "locked_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove dispatch metadata after all in-flight work is drained."""
    op.drop_index(
        "ix_candidate_processor_deletion_requests_dispatch",
        table_name="candidate_processor_deletion_requests",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_status_metadata"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_status_metadata"),
        "candidate_processor_deletion_requests",
        "(status = 'pending' AND status_changed_at IS NULL "
        "AND status_changed_by_subject IS NULL AND resolution_code IS NULL) "
        "OR (status = 'completed' AND status_changed_at IS NOT NULL "
        "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NULL) "
        "OR (status IN ('exception', 'waived') AND status_changed_at IS NOT NULL "
        "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NOT NULL)",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_lease_state"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_attempt_count_nonneg"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_deletion_requests_status"),
        "candidate_processor_deletion_requests",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_deletion_requests_status"),
        "candidate_processor_deletion_requests",
        "status IN ('pending', 'completed', 'exception', 'waived')",
    )
    op.drop_column("candidate_processor_deletion_requests", "last_failure_code")
    op.drop_column("candidate_processor_deletion_requests", "locked_by")
    op.drop_column("candidate_processor_deletion_requests", "locked_at")
    op.drop_column("candidate_processor_deletion_requests", "next_attempt_at")
    op.drop_column("candidate_processor_deletion_requests", "attempt_count")
