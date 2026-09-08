"""SQLAlchemy models for tenant-scoped interview scheduling."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import (
    TSTZRANGE,
    ExcludeConstraint,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PostgreSQLUUID,
)
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.interviews.enums import (
    InterviewParticipantRole,
    InterviewSessionStatus,
)


class InterviewSession(Base):
    """
    A scheduled interview for one tenant-owned application.

    External video and calendar-provider details intentionally do not belong
    here. They will be introduced later through an integration boundary.
    """

    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "scheduled_end_at > scheduled_start_at",
            name="ck_interview_sessions_positive_duration",
        ),
        Index(
            "ix_interview_sessions_tenant_application_start",
            "tenant_id",
            "application_id",
            "scheduled_start_at",
        ),
        Index(
            "ix_interview_sessions_tenant_status_start",
            "tenant_id",
            "status",
            "scheduled_start_at",
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
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheduled_start_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    scheduled_end_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[InterviewSessionStatus] = mapped_column(
        Enum(
            InterviewSessionStatus,
            name="interview_session_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=InterviewSessionStatus.SCHEDULED,
        server_default=InterviewSessionStatus.SCHEDULED.value,
    )

    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
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


class InterviewParticipant(Base):
    """
    An internal user reserved for one interview session.

    `scheduled_time_range` duplicates the session interval intentionally. It
    enables a PostgreSQL exclusion constraint that prevents a user from being
    double-booked even under concurrent schedule requests.
    """

    __tablename__ = "interview_participants"
    __table_args__ = (
        UniqueConstraint(
            "interview_session_id",
            "user_id",
            name="uq_interview_participants_session_user",
        ),
        ExcludeConstraint(
            ("tenant_id", "="),
            ("user_id", "="),
            ("scheduled_time_range", "&&"),
            name="excl_interview_participants_user_time_overlap",
            using="gist",
        ),
        Index(
            "ix_interview_participants_tenant_user",
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
    interview_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    role: Mapped[InterviewParticipantRole] = mapped_column(
        Enum(
            InterviewParticipantRole,
            name="interview_participant_role",
            values_callable=lambda roles: [role.value for role in roles],
        ),
        nullable=False,
    )
    scheduled_time_range: Mapped[Range[datetime]] = mapped_column(
        TSTZRANGE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
