"""add webhook event fanout

Revision ID: 50a972104320
Revises: d4b89723466c
Create Date: 2026-09-17 13:03:25.035398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50a972104320'
down_revision: Union[str, Sequence[str], None] = 'd4b89723466c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create independent webhook events and repoint deliveries safely."""
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.String(length=100), nullable=False),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            sa.dialects.postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_webhook_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint(
            "tenant_id",
            "event_type",
            "deduplication_key",
            name="uq_webhook_events_tenant_event_deduplication",
        ),
    )
    op.create_index(
        op.f("ix_webhook_events_tenant_id"),
        "webhook_events",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_events_tenant_event_created_at",
        "webhook_events",
        ["tenant_id", "event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_events_tenant_aggregate",
        "webhook_events",
        ["tenant_id", "aggregate_type", "aggregate_id"],
        unique=False,
    )

    # No delivery worker exists yet, so existing rows would indicate an unsafe
    # manual write. Refuse migration rather than losing delivery provenance.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM webhook_deliveries) THEN
                RAISE EXCEPTION
                    'Cannot migrate existing webhook deliveries without source events';
            END IF;
        END $$;
        """
    )

    op.add_column(
        "webhook_deliveries",
        sa.Column("webhook_event_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_webhook_deliveries_webhook_event_id_webhook_events"),
        "webhook_deliveries",
        "webhook_events",
        ["webhook_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "uq_webhook_deliveries_endpoint_outbox_event",
        "webhook_deliveries",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_webhook_deliveries_outbox_event_id_outbox_events"),
        "webhook_deliveries",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_webhook_deliveries_outbox_event_id"),
        table_name="webhook_deliveries",
    )
    op.drop_column("webhook_deliveries", "outbox_event_id")
    op.alter_column(
        "webhook_deliveries",
        "webhook_event_id",
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_webhook_deliveries_endpoint_webhook_event",
        "webhook_deliveries",
        ["webhook_endpoint_id", "webhook_event_id"],
    )
    op.create_index(
        op.f("ix_webhook_deliveries_webhook_event_id"),
        "webhook_deliveries",
        ["webhook_event_id"],
        unique=False,
    )


def downgrade() -> None:
    """Restore the former schema only when no delivery history exists."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM webhook_deliveries) THEN
                RAISE EXCEPTION
                    'Cannot downgrade webhook event migration with delivery history';
            END IF;
        END $$;
        """
    )

    op.drop_index(
        op.f("ix_webhook_deliveries_webhook_event_id"),
        table_name="webhook_deliveries",
    )
    op.drop_constraint(
        "uq_webhook_deliveries_endpoint_webhook_event",
        "webhook_deliveries",
        type_="unique",
    )
    op.drop_constraint(
        op.f("fk_webhook_deliveries_webhook_event_id_webhook_events"),
        "webhook_deliveries",
        type_="foreignkey",
    )
    op.drop_column("webhook_deliveries", "webhook_event_id")

    op.add_column(
        "webhook_deliveries",
        sa.Column("outbox_event_id", sa.UUID(), nullable=False),
    )
    op.create_foreign_key(
        op.f("fk_webhook_deliveries_outbox_event_id_outbox_events"),
        "webhook_deliveries",
        "outbox_events",
        ["outbox_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_webhook_deliveries_endpoint_outbox_event",
        "webhook_deliveries",
        ["webhook_endpoint_id", "outbox_event_id"],
    )
    op.create_index(
        op.f("ix_webhook_deliveries_outbox_event_id"),
        "webhook_deliveries",
        ["outbox_event_id"],
        unique=False,
    )

    op.drop_index(
        "ix_webhook_events_tenant_aggregate",
        table_name="webhook_events",
    )
    op.drop_index(
        "ix_webhook_events_tenant_event_created_at",
        table_name="webhook_events",
    )
    op.drop_index(
        op.f("ix_webhook_events_tenant_id"),
        table_name="webhook_events",
    )
    op.drop_table("webhook_events")
