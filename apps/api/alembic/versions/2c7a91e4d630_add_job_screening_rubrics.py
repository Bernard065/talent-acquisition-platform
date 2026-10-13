"""Add shared job-specific screening rubrics."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2c7a91e4d630"
down_revision: str | Sequence[str] | None = "8f3d4b2c1a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store the active rubric on each job and its version on reviews."""
    op.add_column(
        "job_postings",
        sa.Column(
            "screening_rubric",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "job_postings",
        sa.Column(
            "screening_rubric_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.add_column(
        "application_screening_assessments",
        sa.Column("rubric_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Remove shared rubrics and assessment version references."""
    op.drop_column("application_screening_assessments", "rubric_version")
    op.drop_column("job_postings", "screening_rubric_version")
    op.drop_column("job_postings", "screening_rubric")
