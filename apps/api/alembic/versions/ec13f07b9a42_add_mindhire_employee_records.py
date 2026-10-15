"""Add MindHire-owned employee records.

Revision ID: ec13f07b9a42
Revises: b7c2a4d91e6f
Create Date: 2026-10-15 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ec13f07b9a42"
down_revision: str | Sequence[str] | None = "b7c2a4d91e6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


employee_status = postgresql.ENUM(
    "preboarding",
    "active",
    "inactive",
    name="employee_status",
    create_type=False,
)


def upgrade() -> None:
    """Create employee records managed directly in MindHire."""
    employee_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_number", sa.String(length=50), nullable=True),
        sa.Column("work_email", sa.String(length=320), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("job_title", sa.String(length=200), nullable=False),
        sa.Column("department", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("manager_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", employee_status, server_default="preboarding", nullable=False),
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
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name=op.f("fk_employees_application_id_applications"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_employees_candidate_id_candidates"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manager_user_id"],
            ["users.id"],
            name=op.f("fk_employees_manager_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_employees_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_employees")),
        sa.UniqueConstraint("tenant_id", "application_id", name="uq_employees_tenant_application"),
        sa.UniqueConstraint(
            "tenant_id", "employee_number", name="uq_employees_tenant_employee_number"
        ),
        sa.UniqueConstraint("tenant_id", "work_email", name="uq_employees_tenant_work_email"),
    )
    op.create_index(op.f("ix_employees_tenant_id"), "employees", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_employees_application_id"), "employees", ["application_id"], unique=False
    )
    op.create_index(op.f("ix_employees_candidate_id"), "employees", ["candidate_id"], unique=False)
    op.create_index(
        op.f("ix_employees_manager_user_id"), "employees", ["manager_user_id"], unique=False
    )
    op.create_index(
        "ix_employees_tenant_status_created_at",
        "employees",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop MindHire-owned employee records."""
    op.drop_index("ix_employees_tenant_status_created_at", table_name="employees")
    op.drop_index(op.f("ix_employees_manager_user_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_candidate_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_application_id"), table_name="employees")
    op.drop_index(op.f("ix_employees_tenant_id"), table_name="employees")
    op.drop_table("employees")
    employee_status.drop(op.get_bind(), checkfirst=True)
