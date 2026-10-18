"""Add employee onboarding document uploads.

Revision ID: a701c8f4e92d
Revises: f8b1a702c4de
Create Date: 2026-10-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a701c8f4e92d"
down_revision: str | Sequence[str] | None = "f8b1a702c4de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


onboarding_task_document_status = postgresql.ENUM(
    "pending_upload",
    "uploaded",
    "scanning",
    "available",
    "quarantined",
    "rejected",
    name="onboarding_task_document_status",
    create_type=False,
)


def upgrade() -> None:
    """Store safe upload metadata and bind document requirements to task snapshots."""
    onboarding_task_document_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "onboarding_template_tasks",
        sa.Column(
            "requires_document_upload",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "requires_document_upload",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_template_tasks_uploads_employee_only",
        "onboarding_template_tasks",
        "responsible_party = 'employee' OR requires_document_upload = false",
    )
    op.create_check_constraint(
        "ck_onboarding_tasks_uploads_employee_only",
        "onboarding_tasks",
        "responsible_party = 'employee' OR requires_document_upload = false",
    )

    op.create_table(
        "onboarding_task_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("onboarding_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("declared_content_type", sa.String(length=255), nullable=False),
        sa.Column("expected_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            onboarding_task_document_status,
            server_default="pending_upload",
            nullable=False,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "expected_byte_size > 0",
            name="ck_onboarding_task_documents_size_positive",
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_task_id"],
            ["onboarding_tasks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        "ix_onboarding_task_documents_onboarding_task_id",
        "onboarding_task_documents",
        ["onboarding_task_id"],
    )
    op.create_index(
        "ix_onboarding_task_documents_tenant_id",
        "onboarding_task_documents",
        ["tenant_id"],
    )
    op.create_index(
        "ix_onboarding_task_documents_tenant_task_created_at",
        "onboarding_task_documents",
        ["tenant_id", "onboarding_task_id", "created_at"],
    )
    op.create_index(
        "ix_onboarding_task_documents_tenant_status_updated_at",
        "onboarding_task_documents",
        ["tenant_id", "status", "updated_at"],
    )


def downgrade() -> None:
    """Remove onboarding document upload metadata and task requirements."""
    op.drop_index(
        "ix_onboarding_task_documents_tenant_status_updated_at",
        table_name="onboarding_task_documents",
    )
    op.drop_index(
        "ix_onboarding_task_documents_tenant_task_created_at",
        table_name="onboarding_task_documents",
    )
    op.drop_index(
        "ix_onboarding_task_documents_tenant_id",
        table_name="onboarding_task_documents",
    )
    op.drop_index(
        "ix_onboarding_task_documents_onboarding_task_id",
        table_name="onboarding_task_documents",
    )
    op.drop_table("onboarding_task_documents")
    onboarding_task_document_status.drop(op.get_bind(), checkfirst=True)
    op.drop_constraint(
        "ck_onboarding_tasks_uploads_employee_only",
        "onboarding_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_template_tasks_uploads_employee_only",
        "onboarding_template_tasks",
        type_="check",
    )
    op.drop_column("onboarding_tasks", "requires_document_upload")
    op.drop_column("onboarding_template_tasks", "requires_document_upload")
