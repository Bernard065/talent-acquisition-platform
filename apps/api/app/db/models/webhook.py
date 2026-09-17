"""Tenant-scoped webhook endpoint, subscription, and delivery persistence."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.webhooks.enums import (
    WebhookDeliveryStatus,
    WebhookEndpointStatus,
)


class WebhookEndpoint(Base):
    """
    A tenant-owned outbound webhook destination.

    The signing secret is held only by an external vault. PostgreSQL stores its
    opaque reference, never secret material.
    """

    __tablename__ = "webhook_endpoints"
    __table_args__ = (
        UniqueConstraint(
            "credential_reference",
            name="uq_webhook_endpoints_credential_reference",
        ),
        Index(
            "ix_webhook_endpoints_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    credential_reference: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    status: Mapped[WebhookEndpointStatus] = mapped_column(
        Enum(
            WebhookEndpointStatus,
            name="webhook_endpoint_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=WebhookEndpointStatus.ACTIVE,
        server_default=WebhookEndpointStatus.ACTIVE.value,
    )
    created_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class WebhookSubscription(Base):
    """A tenant-selected event type delivered to one webhook endpoint."""

    __tablename__ = "webhook_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "webhook_endpoint_id",
            "event_type",
            name="uq_webhook_subscriptions_tenant_endpoint_event",
        ),
        Index(
            "ix_webhook_subscriptions_tenant_event_enabled",
            "tenant_id",
            "event_type",
            "enabled",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_endpoint_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}


class WebhookDelivery(Base):
    """
    A durable request to deliver one internal outbox event to one endpoint.

    No source payload, response body, authorization header, signature, or
    secret is persisted here. The later delivery worker will construct an
    approved event contract from the referenced outbox event.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="ck_webhook_deliveries_attempts_nonnegative",
        ),
        CheckConstraint(
            "(status != 'delivered') OR delivered_at IS NOT NULL",
            name="ck_webhook_deliveries_delivered_at_required",
        ),
        CheckConstraint(
            "(status != 'failed') OR failed_at IS NOT NULL",
            name="ck_webhook_deliveries_failed_at_required",
        ),
        UniqueConstraint(
            "webhook_endpoint_id",
            "outbox_event_id",
            name="uq_webhook_deliveries_endpoint_outbox_event",
        ),
        Index(
            "ix_webhook_deliveries_status_next_attempt_at",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_webhook_deliveries_endpoint_status",
            "webhook_endpoint_id",
            "status",
        ),
        Index(
            "ix_webhook_deliveries_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    webhook_endpoint_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhook_endpoints.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    outbox_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("outbox_events.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(
            WebhookDeliveryStatus,
            name="webhook_delivery_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        server_default=WebhookDeliveryStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    locked_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    response_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}
