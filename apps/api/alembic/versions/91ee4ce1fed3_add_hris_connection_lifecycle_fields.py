"""add HRIS connection lifecycle fields

Revision ID: 91ee4ce1fed3
Revises: e598614f48e1
Create Date: 2026-09-20 22:03:35.737925

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '91ee4ce1fed3'
down_revision: str | Sequence[str] | None = 'e598614f48e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add logical lifecycle fields to HRIS connections."""
    op.add_column(
        "hris_connections",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hris_connections",
        sa.Column("disabled_by_subject", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "hris_connections",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hris_connections",
        sa.Column("deleted_by_subject", sa.String(length=255), nullable=True),
    )

    op.drop_constraint(
        "uq_hris_connections_tenant_provider_name",
        "hris_connections",
        type_="unique",
    )
    op.create_index(
        "uq_hris_connections_tenant_provider_name_active",
        "hris_connections",
        ["tenant_id", "provider", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_check_constraint(
        "ck_hris_connections_deleted_requires_disabled",
        "hris_connections",
        "(deleted_at IS NULL) OR (status = 'disabled')",
    )


def downgrade() -> None:
    """Remove logical HRIS connection lifecycle fields."""
    op.drop_constraint(
        "ck_hris_connections_deleted_requires_disabled",
        "hris_connections",
        type_="check",
    )
    op.drop_index(
        "uq_hris_connections_tenant_provider_name_active",
        table_name="hris_connections",
    )
    op.create_unique_constraint(
        "uq_hris_connections_tenant_provider_name",
        "hris_connections",
        ["tenant_id", "provider", "name"],
    )

    op.drop_column("hris_connections", "deleted_by_subject")
    op.drop_column("hris_connections", "deleted_at")
    op.drop_column("hris_connections", "disabled_by_subject")
    op.drop_column("hris_connections", "disabled_at")
