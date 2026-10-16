"""Link employee records to authenticated workspace identities.

Revision ID: 9a2e7c4d1f60
Revises: ec13f07b9a42
Create Date: 2026-10-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9a2e7c4d1f60"
down_revision: str | Sequence[str] | None = "ec13f07b9a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add an optional, unique identity link for each employee record."""
    op.add_column(
        "employees",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_employees_user_id_users"),
        "employees",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_unique_constraint("uq_employees_user_id", "employees", ["user_id"])


def downgrade() -> None:
    """Remove employee identity links."""
    op.drop_constraint("uq_employees_user_id", "employees", type_="unique")
    op.drop_constraint(op.f("fk_employees_user_id_users"), "employees", type_="foreignkey")
    op.drop_column("employees", "user_id")
