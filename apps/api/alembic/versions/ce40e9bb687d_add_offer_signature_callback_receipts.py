"""add offer signature callback receipts

Revision ID: ce40e9bb687d
Revises: 91ee4ce1fed3
Create Date: 2026-09-21 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ce40e9bb687d"
down_revision: str | Sequence[str] | None = "91ee4ce1fed3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create immutable receipts for verified e-signature provider callbacks."""
    op.create_table(
        "offer_signature_callback_receipts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("offer_signature_request_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_event_id", sa.String(length=255), nullable=False),
        sa.Column(
            "provider_envelope_reference",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "event_type",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "char_length(payload_sha256) = 64",
            name="ck_offer_signature_callback_receipts_payload_sha256_length",
        ),
        sa.ForeignKeyConstraint(
            ["offer_signature_request_id"],
            ["offer_signature_requests.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_offer_signature_callback_receipts_provider_event",
        ),
    )
    op.create_index(
        "ix_offer_signature_callback_receipts_tenant_id",
        "offer_signature_callback_receipts",
        ["tenant_id"],
    )
    op.create_index(
        "ix_offer_signature_callback_receipts_offer_signature_request_id",
        "offer_signature_callback_receipts",
        ["offer_signature_request_id"],
    )
    op.create_index(
        "ix_offer_signature_callback_receipts_tenant_request_received_at",
        "offer_signature_callback_receipts",
        ["tenant_id", "offer_signature_request_id", "received_at"],
    )

    op.execute(
        """
        CREATE FUNCTION prevent_offer_signature_callback_receipt_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'offer signature callback receipts are immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prevent_offer_signature_callback_receipt_mutation
        BEFORE UPDATE OR DELETE ON offer_signature_callback_receipts
        FOR EACH ROW
        EXECUTE FUNCTION prevent_offer_signature_callback_receipt_mutation();
        """
    )


def downgrade() -> None:
    """Remove callback receipts and their immutable-history protection."""
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_prevent_offer_signature_callback_receipt_mutation "
        "ON offer_signature_callback_receipts"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "prevent_offer_signature_callback_receipt_mutation()"
    )

    op.drop_index(
        "ix_offer_signature_callback_receipts_tenant_request_received_at",
        table_name="offer_signature_callback_receipts",
    )
    op.drop_index(
        "ix_offer_signature_callback_receipts_offer_signature_request_id",
        table_name="offer_signature_callback_receipts",
    )
    op.drop_index(
        "ix_offer_signature_callback_receipts_tenant_id",
        table_name="offer_signature_callback_receipts",
    )
    op.drop_table("offer_signature_callback_receipts")

    # The callback event values remain string-backed to keep Alembic reruns safe
    # on CI databases that may already contain the old enum name.
