"""Add optional prerequisites between onboarding template tasks.

Revision ID: b7c41e92a630
Revises: 9a2e7c4d1f60, a91c7e2d4f60, d2a4f7b91c60
Create Date: 2026-10-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c41e92a630"
down_revision: str | Sequence[str] | None = (
    "9a2e7c4d1f60",
    "a91c7e2d4f60",
    "d2a4f7b91c60",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist prerequisite links and preserve legacy sequential templates."""
    op.create_table(
        "onboarding_template_task_dependencies",
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("prerequisite_task_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "task_id != prerequisite_task_id",
            name="ck_onboarding_template_task_dependencies_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["prerequisite_task_id"],
            ["onboarding_template_tasks.id"],
            name="fk_onboarding_template_task_dependencies_prerequisite_task_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["onboarding_template_tasks.id"],
            name="fk_onboarding_template_task_dependencies_task_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "task_id",
            "prerequisite_task_id",
            name="pk_onboarding_template_task_dependencies",
        ),
    )
    op.create_index(
        "ix_onboarding_template_task_dependencies_prerequisite",
        "onboarding_template_task_dependencies",
        ["prerequisite_task_id"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO onboarding_template_task_dependencies (
                task_id,
                prerequisite_task_id
            )
            SELECT current_task.id, prerequisite_task.id
            FROM onboarding_template_tasks AS current_task
            JOIN onboarding_template_tasks AS prerequisite_task
              ON prerequisite_task.onboarding_template_id = current_task.onboarding_template_id
             AND prerequisite_task.position = current_task.position - 1
            """
        )
    )


def downgrade() -> None:
    """Remove onboarding task prerequisite links."""
    op.drop_index(
        "ix_onboarding_template_task_dependencies_prerequisite",
        table_name="onboarding_template_task_dependencies",
    )
    op.drop_table("onboarding_template_task_dependencies")
