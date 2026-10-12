"""add application saved views

Revision ID: 68e1a0b35c42
Revises: f6d0c4a13b87, 9c0d4e1ab243
Create Date: 2026-10-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "68e1a0b35c42"
down_revision: str | Sequence[str] | None = ("f6d0c4a13b87", "9c0d4e1ab243")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create recruiter-owned saved application filters."""
    op.create_table(
        "application_saved_views",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_name", sa.String(length=80), nullable=False),
        sa.Column("filters", postgresql.JSONB(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_application_saved_views_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_saved_views"),
    )
    op.create_index(
        "ix_application_saved_views_owner_updated",
        "application_saved_views",
        ["tenant_id", "owner_subject", "updated_at"],
    )
    op.create_index(
        "uq_application_saved_views_owner_name",
        "application_saved_views",
        ["tenant_id", "owner_subject", "normalized_name"],
        unique=True,
    )


def downgrade() -> None:
    """Remove recruiter-owned saved application filters."""
    op.drop_index(
        "uq_application_saved_views_owner_name",
        table_name="application_saved_views",
    )
    op.drop_index(
        "ix_application_saved_views_owner_updated",
        table_name="application_saved_views",
    )
    op.drop_table("application_saved_views")
