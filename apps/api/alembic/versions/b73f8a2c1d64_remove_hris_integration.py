"""Remove the external HRIS integration and its persistence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b73f8a2c1d64"
down_revision: str | Sequence[str] | None = (
    "9a2e7c4d1f60",
    "a91c7e2d4f60",
    "d2a4f7b91c60",
    "e2f6a4c1b9d3",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop unused HRIS tables when they contain no integration records."""
    bind = op.get_bind()
    has_legacy_records = bind.execute(
        sa.text(
            """
            SELECT
                EXISTS (SELECT 1 FROM hris_connections)
                OR EXISTS (SELECT 1 FROM hris_handoffs)
                OR EXISTS (
                    SELECT 1
                    FROM candidate_processor_disclosures
                    WHERE source_type = 'hris_handoff'
                       OR processor_code LIKE 'hris.%'
                       OR purpose_code = 'onboarding_handoff'
                )
            """
        )
    ).scalar_one()
    if has_legacy_records:
        raise RuntimeError(
            "HRIS integration records exist. Export or reconcile the legacy "
            "connections, handoffs, and processor-deletion records before "
            "removing this integration. No data was deleted."
        )

    op.drop_constraint(
        op.f("ck_candidate_processor_disclosures_source_type"),
        "candidate_processor_disclosures",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_disclosures_source_type"),
        "candidate_processor_disclosures",
        "source_type IN ('calendar_sync', 'offer_signature')",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_disclosures_purpose_code"),
        "candidate_processor_disclosures",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_disclosures_purpose_code"),
        "candidate_processor_disclosures",
        "purpose_code IN ('interview_scheduling', 'offer_signature')",
    )

    op.drop_table("hris_handoffs")
    op.drop_table("hris_connections")

    postgresql.ENUM(name="hris_handoff_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="hris_connection_status").drop(bind, checkfirst=True)
    postgresql.ENUM(name="hris_provider").drop(bind, checkfirst=True)


def downgrade() -> None:
    """Restore empty HRIS tables and legacy processor disclosure values."""
    bind = op.get_bind()
    hris_provider = postgresql.ENUM(
        "bamboohr",
        "hibob",
        "workday",
        "custom",
        name="hris_provider",
        create_type=False,
    )
    hris_connection_status = postgresql.ENUM(
        "active",
        "disabled",
        name="hris_connection_status",
        create_type=False,
    )
    hris_handoff_status = postgresql.ENUM(
        "pending",
        "processing",
        "succeeded",
        "retryable_failed",
        "failed",
        name="hris_handoff_status",
        create_type=False,
    )
    hris_provider.create(bind, checkfirst=True)
    hris_connection_status.create(bind, checkfirst=True)
    hris_handoff_status.create(bind, checkfirst=True)

    op.create_table(
        "hris_connections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("provider", hris_provider, nullable=False),
        sa.Column(
            "status",
            hris_connection_status,
            server_default="active",
            nullable=False,
        ),
        sa.Column("credential_reference", sa.String(length=500), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_by_subject", sa.String(length=255), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by_subject", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(deleted_at IS NULL) OR (status = 'disabled')",
            name="ck_hris_connections_deleted_requires_disabled",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "credential_reference",
            name="uq_hris_connections_credential_reference",
        ),
    )
    op.create_index(
        "ix_hris_connections_tenant_id",
        "hris_connections",
        ["tenant_id"],
    )
    op.create_index(
        "ix_hris_connections_tenant_status",
        "hris_connections",
        ["tenant_id", "status"],
    )
    op.create_index(
        "uq_hris_connections_tenant_provider_name_active",
        "hris_connections",
        ["tenant_id", "provider", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "hris_handoffs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("hris_connection_id", sa.UUID(), nullable=False),
        sa.Column("onboarding_instance_id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            hris_handoff_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("external_idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("external_employee_reference", sa.String(length=500), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("succeeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(status != 'succeeded') OR succeeded_at IS NOT NULL",
            name="ck_hris_handoffs_succeeded_at_required",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_hris_handoffs_attempt_count_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["hris_connection_id"], ["hris_connections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["onboarding_instance_id"],
            ["onboarding_instances.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "external_idempotency_key",
            name="uq_hris_handoffs_external_idempotency_key",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "onboarding_instance_id",
            name="uq_hris_handoffs_tenant_onboarding_instance",
        ),
    )
    for index_name, columns in (
        ("ix_hris_handoffs_tenant_id", ["tenant_id"]),
        ("ix_hris_handoffs_hris_connection_id", ["hris_connection_id"]),
        ("ix_hris_handoffs_onboarding_instance_id", ["onboarding_instance_id"]),
        ("ix_hris_handoffs_application_id", ["application_id"]),
        (
            "ix_hris_handoffs_tenant_status_updated_at",
            ["tenant_id", "status", "updated_at"],
        ),
        ("ix_hris_handoffs_connection_status", ["hris_connection_id", "status"]),
    ):
        op.create_index(index_name, "hris_handoffs", columns)

    op.drop_constraint(
        op.f("ck_candidate_processor_disclosures_source_type"),
        "candidate_processor_disclosures",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_disclosures_source_type"),
        "candidate_processor_disclosures",
        "source_type IN ('calendar_sync', 'offer_signature', 'hris_handoff')",
    )
    op.drop_constraint(
        op.f("ck_candidate_processor_disclosures_purpose_code"),
        "candidate_processor_disclosures",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_candidate_processor_disclosures_purpose_code"),
        "candidate_processor_disclosures",
        "purpose_code IN ('interview_scheduling', 'offer_signature', "
        "'onboarding_handoff')",
    )
