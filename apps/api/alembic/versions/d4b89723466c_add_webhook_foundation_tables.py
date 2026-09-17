"""add webhook foundation tables

Revision ID: d4b89723466c
Revises: 5311e8b7141d
Create Date: 2026-09-17 08:38:08.127404

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4b89723466c'
down_revision: Union[str, Sequence[str], None] = '5311e8b7141d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create tenant-scoped webhook persistence tables."""
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("credential_reference", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "disabled",
                name="webhook_endpoint_status",
            ),
            server_default="active",
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_webhook_endpoints_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_endpoints")),
        sa.UniqueConstraint(
            "credential_reference",
            name="uq_webhook_endpoints_credential_reference",
        ),
    )
    op.create_index(
        op.f("ix_webhook_endpoints_tenant_id"),
        "webhook_endpoints",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_endpoints_tenant_status",
        "webhook_endpoints",
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("webhook_endpoint_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_webhook_subscriptions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_endpoint_id"],
            ["webhook_endpoints.id"],
            name=op.f(
                "fk_webhook_subscriptions_webhook_endpoint_id_webhook_endpoints"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_subscriptions")),
        sa.UniqueConstraint(
            "tenant_id",
            "webhook_endpoint_id",
            "event_type",
            name="uq_webhook_subscriptions_tenant_endpoint_event",
        ),
    )
    op.create_index(
        op.f("ix_webhook_subscriptions_tenant_id"),
        "webhook_subscriptions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_subscriptions_webhook_endpoint_id"),
        "webhook_subscriptions",
        ["webhook_endpoint_id"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_subscriptions_tenant_event_enabled",
        "webhook_subscriptions",
        ["tenant_id", "event_type", "enabled"],
        unique=False,
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("webhook_endpoint_id", sa.UUID(), nullable=False),
        sa.Column("outbox_event_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "delivering",
                "delivered",
                "failed",
                "disabled",
                name="webhook_delivery_status",
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
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
            "attempts >= 0",
            name="ck_webhook_deliveries_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "(status != 'delivered') OR delivered_at IS NOT NULL",
            name="ck_webhook_deliveries_delivered_at_required",
        ),
        sa.CheckConstraint(
            "(status != 'failed') OR failed_at IS NOT NULL",
            name="ck_webhook_deliveries_failed_at_required",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_webhook_deliveries_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["webhook_endpoint_id"],
            ["webhook_endpoints.id"],
            name=op.f(
                "fk_webhook_deliveries_webhook_endpoint_id_webhook_endpoints"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["outbox_event_id"],
            ["outbox_events.id"],
            name=op.f("fk_webhook_deliveries_outbox_event_id_outbox_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
        sa.UniqueConstraint(
            "webhook_endpoint_id",
            "outbox_event_id",
            name="uq_webhook_deliveries_endpoint_outbox_event",
        ),
    )
    op.create_index(
        op.f("ix_webhook_deliveries_tenant_id"),
        "webhook_deliveries",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_deliveries_webhook_endpoint_id"),
        "webhook_deliveries",
        ["webhook_endpoint_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_webhook_deliveries_outbox_event_id"),
        "webhook_deliveries",
        ["outbox_event_id"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_deliveries_status_next_attempt_at",
        "webhook_deliveries",
        ["status", "next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_deliveries_endpoint_status",
        "webhook_deliveries",
        ["webhook_endpoint_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_webhook_deliveries_tenant_created_at",
        "webhook_deliveries",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Remove webhook persistence tables and enum types."""
    op.drop_index(
        "ix_webhook_deliveries_tenant_created_at",
        table_name="webhook_deliveries",
    )
    op.drop_index(
        "ix_webhook_deliveries_endpoint_status",
        table_name="webhook_deliveries",
    )
    op.drop_index(
        "ix_webhook_deliveries_status_next_attempt_at",
        table_name="webhook_deliveries",
    )
    op.drop_index(
        op.f("ix_webhook_deliveries_outbox_event_id"),
        table_name="webhook_deliveries",
    )
    op.drop_index(
        op.f("ix_webhook_deliveries_webhook_endpoint_id"),
        table_name="webhook_deliveries",
    )
    op.drop_index(
        op.f("ix_webhook_deliveries_tenant_id"),
        table_name="webhook_deliveries",
    )
    op.drop_table("webhook_deliveries")

    op.drop_index(
        "ix_webhook_subscriptions_tenant_event_enabled",
        table_name="webhook_subscriptions",
    )
    op.drop_index(
        op.f("ix_webhook_subscriptions_webhook_endpoint_id"),
        table_name="webhook_subscriptions",
    )
    op.drop_index(
        op.f("ix_webhook_subscriptions_tenant_id"),
        table_name="webhook_subscriptions",
    )
    op.drop_table("webhook_subscriptions")

    op.drop_index(
        "ix_webhook_endpoints_tenant_status",
        table_name="webhook_endpoints",
    )
    op.drop_index(
        op.f("ix_webhook_endpoints_tenant_id"),
        table_name="webhook_endpoints",
    )
    op.drop_table("webhook_endpoints")

    op.execute("DROP TYPE IF EXISTS webhook_delivery_status")
    op.execute("DROP TYPE IF EXISTS webhook_endpoint_status")
