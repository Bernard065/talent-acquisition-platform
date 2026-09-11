"""add recruiting analytics query indexes

Revision ID: ac2a04a0b6e1
Revises: b107361c2b1d
Create Date: 2026-09-12 00:03:06.348059

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ac2a04a0b6e1"
down_revision: str | Sequence[str] | None = "b107361c2b1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add indexes supporting privacy-safe recruiting analytics queries."""
    op.create_index(
        "ix_application_stage_history_tenant_transitioned_at_to_status",
        "application_stage_history",
        ["tenant_id", "transitioned_at", "to_status"],
        unique=False,
    )
    op.create_index(
        "ix_application_stage_history_tenant_to_status_transitioned_at",
        "application_stage_history",
        ["tenant_id", "to_status", "transitioned_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove recruiting analytics query indexes."""
    op.drop_index(
        "ix_application_stage_history_tenant_to_status_transitioned_at",
        table_name="application_stage_history",
    )
    op.drop_index(
        "ix_application_stage_history_tenant_transitioned_at_to_status",
        table_name="application_stage_history",
    )