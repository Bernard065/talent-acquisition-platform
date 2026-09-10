"""protect published job posting snapshots

Revision ID: 875a9ae0736c
Revises: 1486de3f8469
Create Date: 2026-09-10 13:10:11.896288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '875a9ae0736c'
down_revision: Union[str, Sequence[str], None] = '1486de3f8469'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        CREATE FUNCTION prevent_published_job_posting_snapshot_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL
               AND (
                    NEW.title IS DISTINCT FROM OLD.title
                    OR NEW.description IS DISTINCT FROM OLD.description
                    OR NEW.department IS DISTINCT FROM OLD.department
                    OR NEW.location IS DISTINCT FROM OLD.location
                    OR NEW.employment_type IS DISTINCT FROM OLD.employment_type
               )
            THEN
                RAISE EXCEPTION
                    'Published job posting public snapshot cannot be changed';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_job_postings_protect_published_snapshot
        BEFORE UPDATE ON job_postings
        FOR EACH ROW
        EXECUTE FUNCTION prevent_published_job_posting_snapshot_mutation();
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_job_postings_protect_published_snapshot ON job_postings"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "prevent_published_job_posting_snapshot_mutation()"
    )
