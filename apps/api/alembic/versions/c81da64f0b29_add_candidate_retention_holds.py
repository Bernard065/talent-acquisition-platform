"""Add auditable candidate retention holds.

Revision ID: c81da64f0b29
Revises: bc3a1f994f20
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c81da64f0b29"
down_revision: str | Sequence[str] | None = "bc3a1f994f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create hold records and enforce a single release transition."""
    reason_type = sa.Enum(
        "legal_claim",
        "statutory_obligation",
        "regulatory_request",
        "other_evidence",
        name="candidate_retention_hold_reason",
    )
    op.create_table(
        "candidate_retention_holds",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("reason", reason_type, nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("released_by_subject", sa.String(length=255), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(released_at IS NULL AND released_by_subject IS NULL) OR "
            "(released_at IS NOT NULL AND released_by_subject IS NOT NULL)",
            name=op.f("ck_candidate_retention_holds_release_metadata_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE",
            name=op.f("fk_candidate_retention_holds_tenant_id_tenants"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], ondelete="CASCADE",
            name=op.f("fk_candidate_retention_holds_candidate_id_candidates"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_retention_holds")),
    )
    op.create_index(
        "uq_candidate_retention_hold_one_active_reason",
        "candidate_retention_holds",
        ["tenant_id", "candidate_id", "reason"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    op.create_index(
        "ix_candidate_retention_holds_tenant_candidate_active",
        "candidate_retention_holds",
        ["tenant_id", "candidate_id", "released_at"],
    )
    op.execute(
        """
        CREATE FUNCTION enforce_candidate_retention_hold_release() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.released_at IS NOT NULL
               OR NEW.released_at IS NULL
               OR NEW.released_by_subject IS NULL
               OR (to_jsonb(NEW) - 'released_at' - 'released_by_subject' - 'row_version')
                  IS DISTINCT FROM
                  (to_jsonb(OLD) - 'released_at' - 'released_by_subject' - 'row_version')
            THEN
                RAISE EXCEPTION 'candidate retention hold is append-only except release';
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_candidate_retention_hold_release
        BEFORE UPDATE ON candidate_retention_holds
        FOR EACH ROW EXECUTE FUNCTION enforce_candidate_retention_hold_release();
        """
    )


def downgrade() -> None:
    """Remove hold storage and its database-enforced lifecycle guard."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_candidate_retention_hold_release "
        "ON candidate_retention_holds"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_candidate_retention_hold_release()")
    op.drop_index(
        "ix_candidate_retention_holds_tenant_candidate_active",
        table_name="candidate_retention_holds",
    )
    op.drop_index(
        "uq_candidate_retention_hold_one_active_reason",
        table_name="candidate_retention_holds",
    )
    op.drop_table("candidate_retention_holds")
    sa.Enum(name="candidate_retention_hold_reason").drop(op.get_bind(), checkfirst=True)
