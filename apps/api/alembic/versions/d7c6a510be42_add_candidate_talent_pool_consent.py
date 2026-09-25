"""Add immutable purpose-specific talent-pool consent evidence.

Revision ID: d7c6a510be42
Revises: c81da64f0b29
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7c6a510be42"
down_revision: str | Sequence[str] | None = "c81da64f0b29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Persist explicit consent events without changing generic consent data."""
    event_type = sa.Enum(
        "granted",
        "renewed",
        "withdrawn",
        name="candidate_talent_pool_consent_event_type",
    )
    capture_method = sa.Enum(
        "candidate_portal",
        "signed_form",
        "email_confirmation",
        "recruiter_recorded",
        "erasure_request",
        name="candidate_talent_pool_capture_method",
    )
    op.create_table(
        "candidate_talent_pool_consent_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("capture_method", capture_method, nullable=False),
        sa.Column("notice_version", sa.String(length=100), nullable=True),
        sa.Column("recorded_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(event_type = 'withdrawn' OR notice_version IS NOT NULL) AND "
            "(capture_method <> 'erasure_request' OR event_type = 'withdrawn')",
            name=op.f(
                "ck_candidate_talent_pool_consent_events_consent_provenance_consistent"
            ),
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name=op.f(
                "ck_candidate_talent_pool_consent_events_event_version_positive"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
            name=op.f("fk_candidate_talent_pool_consent_events_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            ondelete="CASCADE",
            name=op.f(
                "fk_candidate_talent_pool_consent_events_candidate_id_candidates"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_candidate_talent_pool_consent_events")
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "event_version",
            name=op.f("uq_candidate_talent_pool_consent_version"),
        ),
    )
    op.create_index(
        "ix_candidate_talent_pool_consent_latest",
        "candidate_talent_pool_consent_events",
        ["tenant_id", "candidate_id", sa.text("event_version DESC")],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_candidate_talent_pool_consent_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'Candidate talent-pool consent events are immutable.'
                USING ERRCODE = '55000';
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_candidate_talent_pool_consent_events_immutable
        BEFORE UPDATE OR DELETE ON candidate_talent_pool_consent_events
        FOR EACH ROW
        EXECUTE FUNCTION prevent_candidate_talent_pool_consent_mutation();
        """
    )


def downgrade() -> None:
    """Drop the consent-event guard and storage."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_candidate_talent_pool_consent_events_immutable "
        "ON candidate_talent_pool_consent_events"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_candidate_talent_pool_consent_mutation()"
    )
    op.drop_index(
        "ix_candidate_talent_pool_consent_latest",
        table_name="candidate_talent_pool_consent_events",
    )
    op.drop_table("candidate_talent_pool_consent_events")
    sa.Enum(name="candidate_talent_pool_capture_method").drop(
        op.get_bind(), checkfirst=True
    )
    sa.Enum(name="candidate_talent_pool_consent_event_type").drop(
        op.get_bind(), checkfirst=True
    )
