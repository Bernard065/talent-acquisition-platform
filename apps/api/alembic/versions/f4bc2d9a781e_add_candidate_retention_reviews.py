"""Add immutable candidate-level retention review evidence.

Revision ID: f4bc2d9a781e
Revises: d7c6a510be42
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4bc2d9a781e"
down_revision: str | Sequence[str] | None = "d7c6a510be42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create append-only review evidence and prohibit direct mutation/deletion."""
    purpose_type = sa.Enum(
        "unsuccessful_applicant",
        "withdrawn_applicant",
        "talent_pool",
        "hired_recruiting_copy",
        name="candidate_retention_review_purpose",
    )
    disposition_type = sa.Enum(
        "retain",
        "defer",
        "recommend_manual_erasure",
        name="candidate_retention_review_disposition",
    )
    reason_type = sa.Enum(
        "not_yet_due",
        "active_workflow",
        "legal_hold",
        "ongoing_lawful_basis",
        "employee_record_obligation",
        "processor_action_pending",
        "backup_restore_review_pending",
        "review_complete",
        name="candidate_retention_review_reason",
    )

    op.create_table(
        "candidate_retention_reviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("policy_id", sa.UUID(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("unsuccessful_applicant_days", sa.Integer(), nullable=False),
        sa.Column("withdrawn_applicant_days", sa.Integer(), nullable=False),
        sa.Column("talent_pool_days", sa.Integer(), nullable=False),
        sa.Column("hired_recruiting_copy_days", sa.Integer(), nullable=False),
        sa.Column("review_number", sa.Integer(), nullable=False),
        sa.Column("purpose", purpose_type, nullable=False),
        sa.Column("disposition", disposition_type, nullable=False),
        sa.Column("reason_code", reason_type, nullable=False),
        sa.Column("active_matters_reviewed", sa.Boolean(), nullable=False),
        sa.Column("legal_holds_reviewed", sa.Boolean(), nullable=False),
        sa.Column("other_lawful_basis_reviewed", sa.Boolean(), nullable=False),
        sa.Column("employee_obligations_reviewed", sa.Boolean(), nullable=False),
        sa.Column("external_processors_reviewed", sa.Boolean(), nullable=False),
        sa.Column("backup_restore_safeguards_reviewed", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "review_number >= 1 AND policy_version >= 1",
            name=op.f("ck_candidate_retention_reviews_review_number_and_policy_version_positive"),
        ),
        sa.CheckConstraint(
            "unsuccessful_applicant_days BETWEEN 1 AND 3650 AND "
            "withdrawn_applicant_days BETWEEN 1 AND 3650 AND "
            "talent_pool_days BETWEEN 1 AND 3650 AND "
            "hired_recruiting_copy_days BETWEEN 1 AND 3650",
            name=op.f("ck_candidate_retention_reviews_policy_snapshot_intervals_valid"),
        ),
        sa.CheckConstraint(
            "(disposition = 'recommend_manual_erasure' AND "
            "reason_code = 'review_complete' AND next_review_at IS NULL AND "
            "active_matters_reviewed AND legal_holds_reviewed AND "
            "other_lawful_basis_reviewed AND employee_obligations_reviewed AND "
            "external_processors_reviewed AND backup_restore_safeguards_reviewed) OR "
            "(disposition IN ('retain', 'defer') AND "
            "reason_code <> 'review_complete' AND next_review_at IS NOT NULL)",
            name=op.f("ck_candidate_retention_reviews_review_disposition_consistent"),
        ),
        sa.CheckConstraint(
            "next_review_at IS NULL OR next_review_at > reviewed_at",
            name=op.f("ck_candidate_retention_reviews_next_review_after_reviewed_at"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_retention_reviews_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_retention_reviews_candidate_id_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["policy_id"],
            ["candidate_retention_policies.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_retention_reviews_policy_id_candidate_retention_policies"),
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_candidate_retention_reviews"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "review_number",
            name=op.f("uq_candidate_retention_review_tenant_candidate_number"),
        ),
    )
    op.create_index(
        "ix_candidate_retention_reviews_tenant_candidate_number",
        "candidate_retention_reviews",
        ["tenant_id", "candidate_id", sa.text("review_number DESC")],
        unique=False,
    )
    op.execute(
        """
        CREATE FUNCTION prevent_candidate_retention_review_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'candidate retention review evidence is immutable';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_candidate_retention_review_immutable
        BEFORE UPDATE OR DELETE ON candidate_retention_reviews
        FOR EACH ROW EXECUTE FUNCTION prevent_candidate_retention_review_mutation();
        """
    )


def downgrade() -> None:
    """Remove the review evidence table and its immutability guard."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_candidate_retention_review_immutable "
        "ON candidate_retention_reviews"
    )
    op.execute("DROP FUNCTION IF EXISTS prevent_candidate_retention_review_mutation()")
    op.drop_index(
        "ix_candidate_retention_reviews_tenant_candidate_number",
        table_name="candidate_retention_reviews",
    )
    op.drop_table("candidate_retention_reviews")
    sa.Enum(name="candidate_retention_review_reason").drop(
        op.get_bind(),
        checkfirst=True,
    )
    sa.Enum(name="candidate_retention_review_disposition").drop(
        op.get_bind(),
        checkfirst=True,
    )
    sa.Enum(name="candidate_retention_review_purpose").drop(
        op.get_bind(),
        checkfirst=True,
    )
