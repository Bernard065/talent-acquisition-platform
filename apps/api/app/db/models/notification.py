"""Tenant-scoped notification preferences and delivery intents."""

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
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationStatus,
)


class NotificationPreference(Base):
    """A user's tenant-scoped opt-in preference for one notification event."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "event_type",
            "channel",
            name="uq_notification_preferences_tenant_user_event_channel",
        ),
        Index(
            "ix_notification_preferences_tenant_user",
            "tenant_id",
            "user_id",
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
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(
            NotificationChannel,
            name="notification_channel",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
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


class Notification(Base):
    """
    A durable delivery intent for one internal recipient.

    It stores only event and entity references—not rendered email content,
    candidate PII, compensation, or private feedback. The delivery worker will
    resolve approved template data at send time through a dedicated policy.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "attempts >= 0",
            name="ck_notifications_attempts_non_negative",
        ),
        CheckConstraint(
            "(status != 'sent') OR sent_at IS NOT NULL",
            name="ck_notifications_sent_at_required",
        ),
        CheckConstraint(
            "(status != 'failed') OR failed_at IS NOT NULL",
            name="ck_notifications_failed_at_required",
        ),
        CheckConstraint(
            "(status != 'cancelled') OR cancelled_at IS NOT NULL",
            name="ck_notifications_cancelled_at_required",
        ),
        UniqueConstraint(
            "tenant_id",
            "recipient_user_id",
            "channel",
            "event_type",
            "deduplication_key",
            name="uq_notifications_tenant_recipient_event_deduplication",
        ),
        Index(
            "ix_notifications_tenant_status_scheduled_at",
            "tenant_id",
            "status",
            "scheduled_at",
        ),
        Index(
            "ix_notifications_status_next_attempt_at",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_notifications_recipient_status",
            "recipient_user_id",
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
    recipient_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        PostgreSQLEnum(
            NotificationChannel,
            name="notification_channel",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=False,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(
            NotificationStatus,
            name="notification_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )

    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    template_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # SHA-256 digest of the stable event/recipient identity, never a raw key.
    deduplication_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
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
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
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
