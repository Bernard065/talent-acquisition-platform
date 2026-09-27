"""Add append-only candidate retention execution evidence.

Revision ID: 82b7ce31af49
Revises: f4bc2d9a781e
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "82b7ce31af49"
down_revision: str | Sequence[str] | None = "f4bc2d9a781e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist each reviewed erasure execution exactly once per candidate."""
    op.create_table(
        "candidate_retention_executions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("review_id", sa.UUID(), nullable=False),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("executed_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "review_number >= 1 AND policy_version >= 1",
            name=op.f(
                "ck_candidate_retention_executions_review_and_policy_versions_positive"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_retention_executions_candidate_id_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["candidate_retention_reviews.id"],
            ondelete="RESTRICT",
            name=op.f(
                "fk_candidate_retention_executions_review_id_candidate_retention_reviews"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_retention_executions_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_candidate_retention_executions")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            name=op.f("uq_candidate_retention_execution_tenant_candidate"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "review_id",
            name=op.f("uq_candidate_retention_execution_tenant_review"),
        ),
    )
    op.create_index(
        "ix_candidate_retention_executions_tenant_executed_at",
        "candidate_retention_executions",
        ["tenant_id", "executed_at"],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION prevent_candidate_retention_execution_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'candidate retention execution evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_candidate_retention_execution_immutable
        BEFORE UPDATE OR DELETE ON candidate_retention_executions
        FOR EACH ROW EXECUTE FUNCTION prevent_candidate_retention_execution_mutation()
        """
    )


def downgrade() -> None:
    """Remove the execution table and its immutability guard."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_candidate_retention_execution_immutable "
        "ON candidate_retention_executions"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_candidate_retention_execution_mutation()"
    )
    op.drop_index(
        "ix_candidate_retention_executions_tenant_executed_at",
        table_name="candidate_retention_executions",
    )
    op.drop_table("candidate_retention_executions")
