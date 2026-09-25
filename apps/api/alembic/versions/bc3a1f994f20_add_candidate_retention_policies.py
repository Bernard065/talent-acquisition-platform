"""Add versioned candidate-retention policy schedules.

Revision ID: bc3a1f994f20
Revises: a1d54e799802
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bc3a1f994f20"
down_revision: str | Sequence[str] | None = "a1d54e799802"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tenant policy storage without changing or erasing existing records."""
    policy_status = sa.Enum("draft", "active", "retired", name="candidate_retention_policy_status")
    policy_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "candidate_retention_policies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", policy_status, server_default="draft", nullable=False),
        sa.Column(
            "unsuccessful_applicant_days", sa.Integer(), server_default="365", nullable=False
        ),
        sa.Column("withdrawn_applicant_days", sa.Integer(), server_default="365", nullable=False),
        sa.Column("talent_pool_days", sa.Integer(), server_default="365", nullable=False),
        sa.Column("hired_recruiting_copy_days", sa.Integer(), server_default="90", nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("activated_by_subject", sa.String(length=255), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "policy_version >= 1",
            name=op.f("ck_candidate_retention_policies_policy_version_positive"),
        ),
        sa.CheckConstraint(
            "unsuccessful_applicant_days BETWEEN 1 AND 3650",
            name=op.f("ck_candidate_retention_policies_unsuccessful_days_valid"),
        ),
        sa.CheckConstraint(
            "withdrawn_applicant_days BETWEEN 1 AND 3650",
            name=op.f("ck_candidate_retention_policies_withdrawn_days_valid"),
        ),
        sa.CheckConstraint(
            "talent_pool_days BETWEEN 1 AND 3650",
            name=op.f("ck_candidate_retention_policies_talent_pool_days_valid"),
        ),
        sa.CheckConstraint(
            "hired_recruiting_copy_days BETWEEN 1 AND 3650",
            name=op.f("ck_candidate_retention_policies_hired_copy_days_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND activated_by_subject IS NULL) "
            "OR (status IN ('active', 'retired') AND activated_at IS NOT NULL "
            "AND activated_by_subject IS NOT NULL)",
            name=op.f("ck_candidate_retention_policies_activation_metadata_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_retention_policies_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_retention_policies")),
        sa.UniqueConstraint(
            "tenant_id",
            "policy_version",
            name=op.f("uq_candidate_retention_policy_tenant_version"),
        ),
    )
    op.create_index(
        "uq_candidate_retention_policy_one_active_per_tenant",
        "candidate_retention_policies",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_candidate_retention_policy_tenant_status",
        "candidate_retention_policies",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    """Drop policy storage."""
    op.drop_index(
        "ix_candidate_retention_policy_tenant_status",
        table_name="candidate_retention_policies",
    )
    op.drop_index(
        "uq_candidate_retention_policy_one_active_per_tenant",
        table_name="candidate_retention_policies",
    )
    op.drop_table("candidate_retention_policies")
    sa.Enum(name="candidate_retention_policy_status").drop(op.get_bind(), checkfirst=True)
