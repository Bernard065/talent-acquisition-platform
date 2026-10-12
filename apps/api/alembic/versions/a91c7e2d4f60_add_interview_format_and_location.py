"""add interview format and location

Revision ID: a91c7e2d4f60
Revises: 68e1a0b35c42
Create Date: 2026-10-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a91c7e2d4f60"
down_revision: str | Sequence[str] | None = "68e1a0b35c42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add interview format and location details."""
    interview_format = postgresql.ENUM(
        "online",
        "in_person",
        name="interview_format",
    )
    interview_format.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "interview_sessions",
        sa.Column("format", interview_format, nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("meeting_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("location", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Remove interview format and location details."""
    op.drop_column("interview_sessions", "location")
    op.drop_column("interview_sessions", "meeting_url")
    op.drop_column("interview_sessions", "format")
    postgresql.ENUM(name="interview_format").drop(op.get_bind(), checkfirst=True)
