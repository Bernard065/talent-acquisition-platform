"""add offer signature requests

Revision ID: b43d53402ebd
Revises: 50a972104320
Create Date: 2026-09-17 21:13:09.083762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b43d53402ebd'
down_revision: Union[str, Sequence[str], None] = '50a972104320'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create offer signature persistence and immutable history enforcement."""
    offer_signature_status = sa.Enum(
        "draft",
        "sent",
        "signed",
        "declined",
        "voided",
        "expired",
        name="offer_signature_status",
    )
    offer_signature_event_type = sa.Enum(
        "created",
        "sent",
        "signed",
        "declined",
        "voided",
        "expired",
        name="offer_signature_event_type",
    )

    offer_signature_status.create(op.get_bind(), checkfirst=True)
    offer_signature_event_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "offer_signature_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("offer_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column(
            "provider_envelope_reference",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column("document_reference", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "sent",
                "signed",
                "declined",
                "voided",
                "expired",
                name="offer_signature_status",
                create_type=False,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("offer_version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("base_salary", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "pay_period",
            sa.Enum(
                "hourly",
                "weekly",
                "biweekly",
                "monthly",
                "annually",
                name="offer_pay_period",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("bonus_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("proposed_start_date", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "char_length(currency) = 3",
            name="ck_offer_signature_requests_currency_length",
        ),
        sa.CheckConstraint(
            "base_salary > 0",
            name="ck_offer_signature_requests_base_salary_positive",
        ),
        sa.CheckConstraint(
            "bonus_amount IS NULL OR bonus_amount >= 0",
            name="ck_offer_signature_requests_bonus_amount_nonnegative",
        ),
        sa.CheckConstraint(
            "(status != 'sent') OR sent_at IS NOT NULL",
            name="ck_offer_signature_requests_sent_at_required",
        ),
        sa.CheckConstraint(
            "(status != 'signed') OR signed_at IS NOT NULL",
            name="ck_offer_signature_requests_signed_at_required",
        ),
        sa.CheckConstraint(
            "(status != 'declined') OR declined_at IS NOT NULL",
            name="ck_offer_signature_requests_declined_at_required",
        ),
        sa.CheckConstraint(
            "(status != 'voided') OR voided_at IS NOT NULL",
            name="ck_offer_signature_requests_voided_at_required",
        ),
        sa.CheckConstraint(
            "(status != 'expired') OR expired_at IS NOT NULL",
            name="ck_offer_signature_requests_expired_at_required",
        ),
        sa.ForeignKeyConstraint(
            ["offer_id"],
            ["offers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_envelope_reference"),
        sa.UniqueConstraint(
            "tenant_id",
            "offer_id",
            "offer_version",
            name="uq_offer_signature_requests_tenant_offer_version",
        ),
    )
    op.create_index(
        "ix_offer_signature_requests_tenant_id",
        "offer_signature_requests",
        ["tenant_id"],
    )
    op.create_index(
        "ix_offer_signature_requests_offer_id",
        "offer_signature_requests",
        ["offer_id"],
    )
    op.create_index(
        "ix_offer_signature_requests_tenant_offer_status",
        "offer_signature_requests",
        ["tenant_id", "offer_id", "status"],
    )
    op.create_index(
        "ix_offer_signature_requests_tenant_status_expiry",
        "offer_signature_requests",
        ["tenant_id", "status", "expires_at"],
    )

    op.create_table(
        "offer_signature_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("offer_signature_request_id", sa.UUID(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "created",
                "sent",
                "signed",
                "declined",
                "voided",
                "expired",
                name="offer_signature_event_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "from_status",
            sa.Enum(
                "draft",
                "sent",
                "signed",
                "declined",
                "voided",
                "expired",
                name="offer_signature_status",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "draft",
                "sent",
                "signed",
                "declined",
                "voided",
                "expired",
                name="offer_signature_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("occurred_by_subject", sa.String(length=255), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["offer_signature_request_id"],
            ["offer_signature_requests.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_offer_signature_history_tenant_id",
        "offer_signature_history",
        ["tenant_id"],
    )
    op.create_index(
        "ix_offer_signature_history_offer_signature_request_id",
        "offer_signature_history",
        ["offer_signature_request_id"],
    )
    op.create_index(
        "ix_offer_signature_history_tenant_request_occurred_at",
        "offer_signature_history",
        ["tenant_id", "offer_signature_request_id", "occurred_at"],
    )

    op.execute(
        """
        CREATE FUNCTION prevent_offer_signature_history_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'offer signature history is immutable';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_prevent_offer_signature_history_mutation
        BEFORE UPDATE OR DELETE ON offer_signature_history
        FOR EACH ROW
        EXECUTE FUNCTION prevent_offer_signature_history_mutation();
        """
    )


def downgrade() -> None:
    """Remove offer signature persistence."""
    op.execute(
        "DROP TRIGGER IF EXISTS "
        "trg_prevent_offer_signature_history_mutation "
        "ON offer_signature_history"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS prevent_offer_signature_history_mutation()"
    )

    op.drop_index(
        "ix_offer_signature_history_tenant_request_occurred_at",
        table_name="offer_signature_history",
    )
    op.drop_index(
        "ix_offer_signature_history_offer_signature_request_id",
        table_name="offer_signature_history",
    )
    op.drop_index(
        "ix_offer_signature_history_tenant_id",
        table_name="offer_signature_history",
    )
    op.drop_table("offer_signature_history")

    op.drop_index(
        "ix_offer_signature_requests_tenant_status_expiry",
        table_name="offer_signature_requests",
    )
    op.drop_index(
        "ix_offer_signature_requests_tenant_offer_status",
        table_name="offer_signature_requests",
    )
    op.drop_index(
        "ix_offer_signature_requests_offer_id",
        table_name="offer_signature_requests",
    )
    op.drop_index(
        "ix_offer_signature_requests_tenant_id",
        table_name="offer_signature_requests",
    )
    op.drop_table("offer_signature_requests")

    op.execute("DROP TYPE IF EXISTS offer_signature_event_type")
    op.execute("DROP TYPE IF EXISTS offer_signature_status")
