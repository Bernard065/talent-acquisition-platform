"""Track logically deleted webhook endpoints."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f6a8d9e217"
down_revision: str | Sequence[str] | None = "b73f8a2c1d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a durable marker so retired endpoints leave active settings views."""
    op.add_column(
        "webhook_endpoints",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_webhook_endpoints_tenant_deleted",
        "webhook_endpoints",
        ["tenant_id", "deleted_at"],
    )


def downgrade() -> None:
    """Remove the logical deletion marker."""
    op.drop_index(
        "ix_webhook_endpoints_tenant_deleted",
        table_name="webhook_endpoints",
    )
    op.drop_column("webhook_endpoints", "deleted_at")
