"""Merge existing independent migration heads.

Revision ID: c5d9a18e2f60
Revises: 634be0d89f10, 9c0d4e1ab243, ac2a04a0b6e1, bd4dbe2acea1, e598614f48e1, f8b6443d1c61
Create Date: 2026-10-05
"""

from collections.abc import Sequence

revision: str = "c5d9a18e2f60"
down_revision: str | Sequence[str] | None = (
    "634be0d89f10",
    "9c0d4e1ab243",
    "ac2a04a0b6e1",
    "bd4dbe2acea1",
    "e598614f48e1",
    "f8b6443d1c61",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge the independently developed schema changes."""


def downgrade() -> None:
    """Restore the separate migration heads."""
