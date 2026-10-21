"""Add workspace offboarding checklists and task snapshots.

Revision ID: e2f6a4c1b9d3
Revises: d8c1f4a9b702
Create Date: 2026-10-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2f6a4c1b9d3"
down_revision: str | Sequence[str] | None = "d8c1f4a9b702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create editable task definitions and immutable per-cycle task snapshots."""
    op.add_column(
        "employees",
        sa.Column("offboarding_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_employees_offboarding_cycle_id",
        "employees",
        ["offboarding_cycle_id"],
    )

    op.create_table(
        "employee_offboarding_template_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "due_days_before_last_working_day",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
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
        sa.CheckConstraint("position >= 1", name="ck_offboarding_template_task_position"),
        sa.CheckConstraint(
            "due_days_before_last_working_day BETWEEN 0 AND 365",
            name="ck_offboarding_template_task_due_offset",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "position",
            name="uq_employee_offboarding_template_tasks_tenant_position",
        ),
    )
    op.create_index(
        "ix_employee_offboarding_template_tasks_tenant_id",
        "employee_offboarding_template_tasks",
        ["tenant_id"],
    )

    op.create_table(
        "employee_offboarding_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offboarding_cycle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("completion_notes", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_subject", sa.String(length=255), nullable=True),
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
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_employee_offboarding_task_position"),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'blocked')",
            name="ck_employee_offboarding_task_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_task_id"],
            ["employee_offboarding_template_tasks.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["assigned_to_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "offboarding_cycle_id",
            "position",
            name="uq_employee_offboarding_tasks_cycle_position",
        ),
    )
    op.create_index(
        "ix_employee_offboarding_tasks_tenant_id",
        "employee_offboarding_tasks",
        ["tenant_id"],
    )
    op.create_index(
        "ix_employee_offboarding_tasks_employee_id",
        "employee_offboarding_tasks",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_offboarding_tasks_offboarding_cycle_id",
        "employee_offboarding_tasks",
        ["offboarding_cycle_id"],
    )
    op.create_index(
        "ix_employee_offboarding_tasks_assigned_to_user_id",
        "employee_offboarding_tasks",
        ["assigned_to_user_id"],
    )


def downgrade() -> None:
    """Drop checklist task tables and cycle identifiers."""
    op.drop_index(
        "ix_employee_offboarding_tasks_assigned_to_user_id",
        table_name="employee_offboarding_tasks",
    )
    op.drop_index(
        "ix_employee_offboarding_tasks_offboarding_cycle_id",
        table_name="employee_offboarding_tasks",
    )
    op.drop_index(
        "ix_employee_offboarding_tasks_employee_id",
        table_name="employee_offboarding_tasks",
    )
    op.drop_index(
        "ix_employee_offboarding_tasks_tenant_id",
        table_name="employee_offboarding_tasks",
    )
    op.drop_table("employee_offboarding_tasks")
    op.drop_index(
        "ix_employee_offboarding_template_tasks_tenant_id",
        table_name="employee_offboarding_template_tasks",
    )
    op.drop_table("employee_offboarding_template_tasks")
    op.drop_index("ix_employees_offboarding_cycle_id", table_name="employees")
    op.drop_column("employees", "offboarding_cycle_id")
