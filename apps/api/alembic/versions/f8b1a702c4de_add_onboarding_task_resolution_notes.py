"""Persist onboarding blocker notes and responses.

Revision ID: f8b1a702c4de
Revises: f4a7c1d92e63
Create Date: 2026-10-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8b1a702c4de"
down_revision: str | Sequence[str] | None = "f4a7c1d92e63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add current response and immutable note history fields."""
    op.add_column(
        "onboarding_tasks",
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "onboarding_task_history",
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove the onboarding response fields."""
    op.drop_column("onboarding_task_history", "note")
    op.drop_column("onboarding_tasks", "resolution_note")
