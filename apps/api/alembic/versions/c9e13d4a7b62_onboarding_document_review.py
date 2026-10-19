"""Add human review to required onboarding documents.

Revision ID: c9e13d4a7b62
Revises: a701c8f4e92d
Create Date: 2026-10-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9e13d4a7b62"
down_revision: str | Sequence[str] | None = "a701c8f4e92d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

onboarding_task_document_review_status = postgresql.ENUM(
    "not_required",
    "pending_review",
    "accepted",
    "changes_requested",
    name="onboarding_task_document_review_status",
    create_type=False,
)


def upgrade() -> None:
    """Track review requirements, decisions, and employee-facing feedback."""
    onboarding_task_document_review_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "onboarding_template_tasks",
        sa.Column(
            "requires_document_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "requires_document_review",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_template_tasks_review_requires_upload",
        "onboarding_template_tasks",
        "requires_document_review = false OR requires_document_upload = true",
    )
    op.create_check_constraint(
        "ck_onboarding_tasks_review_requires_upload",
        "onboarding_tasks",
        "requires_document_review = false OR requires_document_upload = true",
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column(
            "review_status",
            onboarding_task_document_review_status,
            server_default="not_required",
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column("reviewed_by_subject", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column("review_comment", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_onboarding_task_documents_review_metadata_consistent",
        "onboarding_task_documents",
        "(review_status IN ('not_required', 'pending_review') "
        "AND reviewed_at IS NULL AND reviewed_by_subject IS NULL) OR "
        "(review_status IN ('accepted', 'changes_requested') "
        "AND reviewed_at IS NOT NULL AND reviewed_by_subject IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_onboarding_task_documents_review_requires_clean_file",
        "onboarding_task_documents",
        "review_status NOT IN ('pending_review', 'accepted', 'changes_requested') "
        "OR status = 'available'",
    )


def downgrade() -> None:
    """Remove the onboarding document review lifecycle."""
    op.drop_constraint(
        "ck_onboarding_task_documents_review_requires_clean_file",
        "onboarding_task_documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_task_documents_review_metadata_consistent",
        "onboarding_task_documents",
        type_="check",
    )
    op.drop_column("onboarding_task_documents", "review_comment")
    op.drop_column("onboarding_task_documents", "reviewed_at")
    op.drop_column("onboarding_task_documents", "reviewed_by_subject")
    op.drop_column("onboarding_task_documents", "review_status")
    onboarding_task_document_review_status.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint(
        "ck_onboarding_tasks_review_requires_upload",
        "onboarding_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_template_tasks_review_requires_upload",
        "onboarding_template_tasks",
        type_="check",
    )
    op.drop_column("onboarding_tasks", "requires_document_review")
    op.drop_column("onboarding_template_tasks", "requires_document_review")
