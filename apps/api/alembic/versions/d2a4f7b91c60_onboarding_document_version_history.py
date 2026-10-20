"""Track onboarding document replacements and review attribution.

Revision ID: d2a4f7b91c60
Revises: c9e13d4a7b62
Create Date: 2026-10-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d2a4f7b91c60"
down_revision: str | Sequence[str] | None = "c9e13d4a7b62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist replacement links, revision numbers, and reviewer names."""
    op.add_column(
        "onboarding_task_documents",
        sa.Column("replaces_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column(
            "revision_number",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_task_documents",
        sa.Column("reviewed_by_name", sa.String(length=200), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE onboarding_task_documents AS document "
            "SET reviewed_by_name = users.display_name "
            "FROM users "
            "WHERE users.tenant_id = document.tenant_id "
            "AND users.external_subject = document.reviewed_by_subject "
            "AND document.reviewed_by_subject IS NOT NULL"
        )
    )
    op.create_check_constraint(
        "ck_onboarding_task_documents_revision_positive",
        "onboarding_task_documents",
        "revision_number > 0",
    )
    op.create_check_constraint(
        "ck_onboarding_task_documents_revision_replacement_consistent",
        "onboarding_task_documents",
        "(replaces_document_id IS NULL AND revision_number = 1) OR "
        "(replaces_document_id IS NOT NULL AND revision_number > 1)",
    )
    op.create_check_constraint(
        "ck_onboarding_task_documents_cannot_replace_self",
        "onboarding_task_documents",
        "replaces_document_id IS NULL OR replaces_document_id <> id",
    )
    op.create_unique_constraint(
        "uq_onboarding_task_documents_tenant_task_id_id",
        "onboarding_task_documents",
        ["tenant_id", "onboarding_task_id", "id"],
    )
    op.create_unique_constraint(
        "uq_onboarding_task_documents_replaces_document_id",
        "onboarding_task_documents",
        ["replaces_document_id"],
    )
    op.create_foreign_key(
        "fk_onboarding_task_documents_replacement_parent",
        "onboarding_task_documents",
        "onboarding_task_documents",
        ["tenant_id", "onboarding_task_id", "replaces_document_id"],
        ["tenant_id", "onboarding_task_id", "id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_onboarding_task_documents_tenant_task_revision",
        "onboarding_task_documents",
        ["tenant_id", "onboarding_task_id", "revision_number"],
    )


def downgrade() -> None:
    """Remove onboarding document revision metadata."""
    op.drop_index(
        "ix_onboarding_task_documents_tenant_task_revision",
        table_name="onboarding_task_documents",
    )
    op.drop_constraint(
        "fk_onboarding_task_documents_replacement_parent",
        "onboarding_task_documents",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_onboarding_task_documents_replaces_document_id",
        "onboarding_task_documents",
        type_="unique",
    )
    op.drop_constraint(
        "uq_onboarding_task_documents_tenant_task_id_id",
        "onboarding_task_documents",
        type_="unique",
    )
    op.drop_constraint(
        "ck_onboarding_task_documents_cannot_replace_self",
        "onboarding_task_documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_task_documents_revision_replacement_consistent",
        "onboarding_task_documents",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_task_documents_revision_positive",
        "onboarding_task_documents",
        type_="check",
    )
    op.drop_column("onboarding_task_documents", "reviewed_by_name")
    op.drop_column("onboarding_task_documents", "revision_number")
    op.drop_column("onboarding_task_documents", "replaces_document_id")
