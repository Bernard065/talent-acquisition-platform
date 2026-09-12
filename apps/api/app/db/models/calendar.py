"""Persistence models for external calendar integration state."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
    InterviewCalendarSyncStatus,
)


class CalendarConnection(Base):
    """
    A tenant user's connection to an external calendar provider.

    `credential_reference` points to a secret managed outside this database,
    such as a cloud secret manager. Never persist OAuth access tokens, refresh
    tokens, authorization codes, or provider secrets in this application table.
    """

    __tablename__ = "calendar_connections"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "owner_user_id",
            "provider",
            name="uq_calendar_connections_tenant_owner_provider",
        ),
        Index(
            "ix_calendar_connections_tenant_status",
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
    owner_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider: Mapped[CalendarProvider] = mapped_column(
        Enum(
            CalendarProvider,
            name="calendar_provider",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    status: Mapped[CalendarConnectionStatus] = mapped_column(
        Enum(
            CalendarConnectionStatus,
            name="calendar_connection_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=CalendarConnectionStatus.ACTIVE,
        server_default=CalendarConnectionStatus.ACTIVE.value,
    )

    # An opaque reference, e.g. "vault://tap/calendar/google/connection/<id>".
    credential_reference: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )
    external_calendar_id: Mapped[str | None] = mapped_column(
        String(500),
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


class InterviewCalendarSync(Base):
    """
    Provider-event synchronization state for one interview and connection.

    `external_idempotency_key` is generated once and remains stable for the
    record's lifetime. Provider adapters must use it on every create/update
    attempt so retries cannot create duplicate calendar events.
    """

    __tablename__ = "interview_calendar_syncs"
    __table_args__ = (
        UniqueConstraint(
            "calendar_connection_id",
            "interview_session_id",
            name="uq_interview_calendar_syncs_connection_session",
        ),
        UniqueConstraint(
            "external_idempotency_key",
            name="uq_interview_calendar_syncs_external_idempotency_key",
        ),
        Index(
            "ix_interview_calendar_syncs_tenant_status_updated_at",
            "tenant_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_interview_calendar_syncs_interview_session",
            "interview_session_id",
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
    interview_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    calendar_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("calendar_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[InterviewCalendarSyncStatus] = mapped_column(
        Enum(
            InterviewCalendarSyncStatus,
            name="interview_calendar_sync_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=InterviewCalendarSyncStatus.PENDING,
        server_default=InterviewCalendarSyncStatus.PENDING.value,
    )

    # The provider's opaque event identifier; never use it for authorization.
    external_event_id: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    external_idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default=lambda: str(uuid4()),
    )

    # Version of the interview session represented by the pending sync work.
    desired_interview_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    synced_interview_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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
