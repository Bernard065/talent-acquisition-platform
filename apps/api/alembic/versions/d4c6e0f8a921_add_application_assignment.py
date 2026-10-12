"""add application assignment

Revision ID: d4c6e0f8a921
Revises: b7d3c4e9a621
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4c6e0f8a921"
down_revision: str | Sequence[str] | None = "b7d3c4e9a621"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional tenant-scoped ownership to applications."""
    op.add_column(
        "applications",
        sa.Column("assigned_to_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_assigned_to_user_id_users",
        "applications",
        "users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_applications_tenant_assignee_applied_at",
        "applications",
        ["tenant_id", "assigned_to_user_id", "applied_at", "id"],
    )


def downgrade() -> None:
    """Remove application ownership."""
    op.drop_index(
        "ix_applications_tenant_assignee_applied_at",
        table_name="applications",
    )
    op.drop_constraint(
        "fk_applications_assigned_to_user_id_users",
        "applications",
        type_="foreignkey",
    )
    op.drop_column("applications", "assigned_to_user_id")
