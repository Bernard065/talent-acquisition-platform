"""add Auth0 Organization mapping to tenants

Revision ID: 5a5efc9c7699
Revises: a6f5c2d9e310
Create Date: 2026-10-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5a5efc9c7699"
down_revision: str | Sequence[str] | None = "a6f5c2d9e310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an optional, unique Auth0 Organization mapping per tenant."""
    op.add_column(
        "tenants",
        sa.Column("auth0_organization_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tenants_auth0_organization_id",
        "tenants",
        ["auth0_organization_id"],
    )


def downgrade() -> None:
    """Remove the Auth0 Organization mapping from tenants."""
    op.drop_constraint(
        "uq_tenants_auth0_organization_id",
        "tenants",
        type_="unique",
    )
    op.drop_column("tenants", "auth0_organization_id")
