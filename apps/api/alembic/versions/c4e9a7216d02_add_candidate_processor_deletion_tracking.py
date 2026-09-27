"""Add candidate processor disclosure and deletion tracking.

Revision ID: c4e9a7216d02
Revises: 82b7ce31af49
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4e9a7216d02"
down_revision: str | Sequence[str] | None = "82b7ce31af49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist processor disclosures and downstream erasure work items."""
    op.create_table(
        "candidate_processor_disclosures",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("processor_code", sa.String(length=100), nullable=False),
        sa.Column("purpose_code", sa.String(length=50), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("external_record_reference", sa.String(length=500), nullable=True),
        sa.Column(
            "disclosed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(processor_code) BETWEEN 1 AND 100",
            name=op.f("ck_candidate_processor_disclosures_processor_code_length"),
        ),
        sa.CheckConstraint(
            "length(purpose_code) BETWEEN 1 AND 50",
            name=op.f("ck_candidate_processor_disclosures_purpose_code_length"),
        ),
        sa.CheckConstraint(
            "purpose_code IN ('interview_scheduling', 'offer_signature', "
            "'onboarding_handoff')",
            name=op.f("ck_candidate_processor_disclosures_purpose_code"),
        ),
        sa.CheckConstraint(
            "source_type IN ('calendar_sync', 'offer_signature', 'hris_handoff')",
            name=op.f("ck_candidate_processor_disclosures_source_type"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_processor_disclosures_candidate_id_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_processor_disclosures_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_processor_disclosures")),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name=op.f("uq_candidate_processor_disclosures_tenant_id"),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            name=op.f("uq_candidate_processor_disclosures_source"),
        ),
    )
    op.create_index(
        "ix_candidate_processor_disclosures_tenant_candidate",
        "candidate_processor_disclosures",
        ["tenant_id", "candidate_id"],
        unique=False,
    )
    op.create_index(
        "ix_candidate_processor_disclosures_tenant_processor",
        "candidate_processor_disclosures",
        ["tenant_id", "processor_code"],
        unique=False,
    )

    op.create_table(
        "candidate_processor_deletion_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("disclosure_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("resolution_code", sa.String(length=100), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_changed_by_subject", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'exception', 'waived')",
            name=op.f("ck_candidate_processor_deletion_requests_status"),
        ),
        sa.CheckConstraint(
            "version >= 1",
            name=op.f("ck_candidate_processor_deletion_requests_version_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND status_changed_at IS NULL "
            "AND status_changed_by_subject IS NULL AND resolution_code IS NULL) "
            "OR (status = 'completed' AND status_changed_at IS NOT NULL "
            "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NULL) "
            "OR (status IN ('exception', 'waived') AND status_changed_at IS NOT NULL "
            "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NOT NULL)",
            name=op.f("ck_candidate_processor_deletion_requests_status_metadata"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_processor_deletion_requests_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "disclosure_id"],
            ["candidate_processor_disclosures.tenant_id", "candidate_processor_disclosures.id"],
            ondelete="RESTRICT",
            name=op.f("fk_candidate_processor_deletion_disclosure_tenant"),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_candidate_processor_deletion_requests")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "disclosure_id",
            name=op.f("uq_candidate_processor_deletion_disclosure"),
        ),
    )
    op.create_index(
        "ix_candidate_processor_deletion_requests_tenant_status_created",
        "candidate_processor_deletion_requests",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop processor deletion tracking tables and indexes."""
    op.drop_index(
        "ix_candidate_processor_deletion_requests_tenant_status_created",
        table_name="candidate_processor_deletion_requests",
    )
    op.drop_table("candidate_processor_deletion_requests")
    op.drop_index(
        "ix_candidate_processor_disclosures_tenant_processor",
        table_name="candidate_processor_disclosures",
    )
    op.drop_index(
        "ix_candidate_processor_disclosures_tenant_candidate",
        table_name="candidate_processor_disclosures",
    )
    op.drop_table("candidate_processor_disclosures")
