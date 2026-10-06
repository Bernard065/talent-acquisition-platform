"""Add workspace invitations.

Revision ID: 2f4a6c8d1e30
Revises: c5d9a18e2f60
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "2f4a6c8d1e30"
down_revision: str | Sequence[str] | None = "c5d9a18e2f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = postgresql.ENUM(
    "tenant_admin",
    "recruiter",
    "hiring_manager",
    "interviewer",
    "people_operations",
    "analyst",
    name="user_role",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "workspace_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("invited_by_subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_invitations")),
        sa.CheckConstraint(
            "status in ('pending', 'accepted', 'revoked', 'expired')",
            name=op.f("ck_workspace_invitations_valid_status"),
        ),
    )
    op.create_index(
        op.f("ix_workspace_invitations_tenant_id"), "workspace_invitations", ["tenant_id"]
    )
    op.create_index(
        "uq_workspace_invitations_pending_email",
        "workspace_invitations",
        ["email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_workspace_invitations_pending_email", table_name="workspace_invitations")
    op.drop_index(op.f("ix_workspace_invitations_tenant_id"), table_name="workspace_invitations")
    op.drop_table("workspace_invitations")
