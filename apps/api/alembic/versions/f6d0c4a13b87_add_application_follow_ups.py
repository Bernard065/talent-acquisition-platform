"""add application follow-ups

Revision ID: f6d0c4a13b87
Revises: d4c6e0f8a921
Create Date: 2026-10-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6d0c4a13b87"
down_revision: str | Sequence[str] | None = "d4c6e0f8a921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant-scoped follow-up actions and pending lookup indexes."""
    op.create_table(
        "application_follow_ups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_subject", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_follow_ups_application_id_applications",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_application_follow_ups_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_follow_ups"),
    )
    op.create_index(
        "uq_application_follow_ups_one_pending_per_application",
        "application_follow_ups",
        ["tenant_id", "application_id"],
        unique=True,
        postgresql_where=sa.text("completed_at IS NULL"),
    )
    op.create_index(
        "ix_application_follow_ups_pending_due_at",
        "application_follow_ups",
        ["tenant_id", "due_at", "application_id"],
        postgresql_where=sa.text("completed_at IS NULL"),
    )


def downgrade() -> None:
    """Drop application follow-ups."""
    op.drop_index(
        "ix_application_follow_ups_pending_due_at",
        table_name="application_follow_ups",
    )
    op.drop_index(
        "uq_application_follow_ups_one_pending_per_application",
        table_name="application_follow_ups",
    )
    op.drop_table("application_follow_ups")
