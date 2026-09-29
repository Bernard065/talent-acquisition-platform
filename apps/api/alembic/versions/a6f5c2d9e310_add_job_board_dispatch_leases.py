"""add generation tracking and publication dispatch leases

Revision ID: a6f5c2d9e310
Revises: c1b9a6f3e250
Create Date: 2026-09-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6f5c2d9e310"
down_revision: str | Sequence[str] | None = "c1b9a6f3e250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track desired-state generations and lease per-publication dispatch."""
    op.add_column(
        "job_board_publications",
        sa.Column(
            "desired_generation",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    # Preserve compatibility with already queued foundation events, whose
    # payload version recorded the intent's publication version.
    op.execute(
        "UPDATE job_board_publications "
        "SET desired_generation = version"
    )
    op.add_column(
        "job_board_publications",
        sa.Column(
            "last_synced_generation",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "job_board_publications",
        sa.Column("dispatch_locked_by", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "job_board_publications",
        sa.Column(
            "dispatch_locked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_job_board_publications_dispatch_lease_consistent"),
        "job_board_publications",
        "(dispatch_locked_by IS NULL) = (dispatch_locked_until IS NULL)",
    )


def downgrade() -> None:
    """Remove dispatch leases and desired-state generation tracking."""
    op.drop_constraint(
        op.f("ck_job_board_publications_dispatch_lease_consistent"),
        "job_board_publications",
        type_="check",
    )
    op.drop_column("job_board_publications", "dispatch_locked_until")
    op.drop_column("job_board_publications", "dispatch_locked_by")
    op.drop_column("job_board_publications", "last_synced_generation")
    op.drop_column("job_board_publications", "desired_generation")
