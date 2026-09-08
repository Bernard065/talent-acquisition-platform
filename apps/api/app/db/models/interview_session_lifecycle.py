"""Append-only persistence for interview session lifecycle events."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewLifecycleEventType,
    InterviewSessionStatus,
)


class InterviewSessionLifecycleHistory(Base):
    """Immutable record of a complete, cancel, or reschedule operation."""

    __tablename__ = "interview_session_lifecycle_history"
    __table_args__ = (
        CheckConstraint(
            "(event_type != 'cancelled') OR cancellation_reason IS NOT NULL",
            name="ck_interview_lifecycle_cancellation_reason_required",
        ),
        Index(
            "ix_interview_lifecycle_tenant_session_occurred_at",
            "tenant_id",
            "interview_session_id",
            "occurred_at",
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

    event_type: Mapped[InterviewLifecycleEventType] = mapped_column(
        Enum(
            InterviewLifecycleEventType,
            name="interview_lifecycle_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    from_status: Mapped[InterviewSessionStatus] = mapped_column(
        Enum(
            InterviewSessionStatus,
            name="interview_session_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    to_status: Mapped[InterviewSessionStatus] = mapped_column(
        Enum(
            InterviewSessionStatus,
            name="interview_session_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )

    previous_scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    previous_scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancellation_reason: Mapped[InterviewCancellationReason | None] = mapped_column(
        Enum(
            InterviewCancellationReason,
            name="interview_cancellation_reason",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )

    occurred_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
