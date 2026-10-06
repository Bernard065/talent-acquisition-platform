"""Make tenant organization mapping provider-neutral.

Revision ID: 9c0d4e1ab243
Revises: 5a5efc9c7699
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9c0d4e1ab243"
down_revision: str | Sequence[str] | None = "5a5efc9c7699"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename the external organization mapping without changing its values."""
    op.drop_constraint(
        "uq_tenants_auth0_organization_id",
        "tenants",
        type_="unique",
    )
    op.alter_column(
        "tenants",
        "auth0_organization_id",
        new_column_name="identity_provider_organization_id",
    )
    op.create_unique_constraint(
        "uq_tenants_identity_provider_organization_id",
        "tenants",
        ["identity_provider_organization_id"],
    )


def downgrade() -> None:
    """Restore the historical column name."""
    op.drop_constraint(
        "uq_tenants_identity_provider_organization_id",
        "tenants",
        type_="unique",
    )
    op.alter_column(
        "tenants",
        "identity_provider_organization_id",
        new_column_name="auth0_organization_id",
    )
    op.create_unique_constraint(
        "uq_tenants_auth0_organization_id",
        "tenants",
        ["auth0_organization_id"],
    )
