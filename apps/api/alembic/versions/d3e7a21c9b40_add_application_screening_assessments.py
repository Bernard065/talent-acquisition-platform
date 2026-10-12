"""add recruiter screening assessments

Revision ID: d3e7a21c9b40
Revises: b31e6c4d8a90
Create Date: 2026-10-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3e7a21c9b40"
down_revision: str | Sequence[str] | None = "b31e6c4d8a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable, tenant-scoped recruiter scorecards."""
    op.create_table(
        "application_screening_assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=False),
        sa.Column("overall_rating", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.String(length=16), nullable=False),
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "overall_rating BETWEEN 1 AND 5",
            name="ck_application_screening_assessments_rating_range",
        ),
        sa.CheckConstraint(
            "recommendation in ('advance', 'hold', 'reject')",
            name="ck_application_screening_assessments_recommendation",
        ),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 5000",
            name="ck_application_screening_assessments_summary_length",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "application_id",
            "reviewer_user_id",
            name="uq_application_screening_assessments_reviewer",
        ),
    )
    op.create_index(
        "ix_application_screening_assessments_tenant_id",
        "application_screening_assessments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_application_screening_assessments_application_id",
        "application_screening_assessments",
        ["application_id"],
    )
    op.create_index(
        "ix_application_screening_assessments_reviewer_user_id",
        "application_screening_assessments",
        ["reviewer_user_id"],
    )
    op.create_index(
        "ix_screening_assessments_tenant_app_submitted",
        "application_screening_assessments",
        ["tenant_id", "application_id", "submitted_at"],
    )


def downgrade() -> None:
    """Remove recruiter screening scorecards."""
    op.drop_index(
        "ix_screening_assessments_tenant_app_submitted",
        table_name="application_screening_assessments",
    )
    op.drop_index(
        "ix_application_screening_assessments_reviewer_user_id",
        table_name="application_screening_assessments",
    )
    op.drop_index(
        "ix_application_screening_assessments_application_id",
        table_name="application_screening_assessments",
    )
    op.drop_index(
        "ix_application_screening_assessments_tenant_id",
        table_name="application_screening_assessments",
    )
    op.drop_table("application_screening_assessments")
