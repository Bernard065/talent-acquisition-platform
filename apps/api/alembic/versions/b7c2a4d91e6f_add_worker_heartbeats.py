"""Add durable worker liveness timestamps.

Revision ID: b7c2a4d91e6f
Revises: 7d3a9c1f5e20
Create Date: 2026-10-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c2a4d91e6f"
down_revision: str | Sequence[str] | None = "7d3a9c1f5e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the worker heartbeat registry."""
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_name", sa.String(length=100), nullable=False),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("worker_name", name=op.f("pk_worker_heartbeats")),
    )


def downgrade() -> None:
    """Remove the worker heartbeat registry."""
    op.drop_table("worker_heartbeats")
