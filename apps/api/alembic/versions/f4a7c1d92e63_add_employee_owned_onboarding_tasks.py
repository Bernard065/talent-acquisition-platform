"""Add employee ownership to onboarding task definitions and snapshots.

Revision ID: f4a7c1d92e63
Revises: 9a2e7c4d1f60, a91c7e2d4f60
Create Date: 2026-10-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f4a7c1d92e63"
down_revision: str | Sequence[str] | None = (
    "9a2e7c4d1f60",
    "a91c7e2d4f60",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


onboarding_task_responsibility = postgresql.ENUM(
    "workspace",
    "employee",
    name="onboarding_task_responsibility",
    create_type=False,
)


def upgrade() -> None:
    """Add backward-compatible task responsibility snapshots."""
    onboarding_task_responsibility.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "onboarding_template_tasks",
        sa.Column(
            "responsible_party",
            onboarding_task_responsibility,
            server_default="workspace",
            nullable=False,
        ),
    )
    op.add_column(
        "onboarding_tasks",
        sa.Column(
            "responsible_party",
            onboarding_task_responsibility,
            server_default="workspace",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_onboarding_template_tasks_employee_no_assignee_role",
        "onboarding_template_tasks",
        "responsible_party != 'employee' OR default_assignee_role IS NULL",
    )
    op.create_check_constraint(
        "ck_onboarding_tasks_employee_unassigned",
        "onboarding_tasks",
        "responsible_party != 'employee' OR assignee_user_id IS NULL",
    )


def downgrade() -> None:
    """Remove employee responsibility metadata."""
    op.drop_constraint(
        "ck_onboarding_tasks_employee_unassigned",
        "onboarding_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_onboarding_template_tasks_employee_no_assignee_role",
        "onboarding_template_tasks",
        type_="check",
    )
    op.drop_column("onboarding_tasks", "responsible_party")
    op.drop_column("onboarding_template_tasks", "responsible_party")
    onboarding_task_responsibility.drop(op.get_bind(), checkfirst=True)
