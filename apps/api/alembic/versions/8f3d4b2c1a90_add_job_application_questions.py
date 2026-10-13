"""Add job-specific application questions and submitted answer snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8f3d4b2c1a90"
down_revision: str | Sequence[str] | None = "d3e7a21c9b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add JSON columns with empty defaults for existing rows."""
    op.add_column(
        "job_postings",
        sa.Column(
            "application_questions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "applications",
        sa.Column(
            "answers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove the question configuration and answer snapshots."""
    op.drop_column("applications", "answers")
    op.drop_column("job_postings", "application_questions")

