"""SQLAlchemy model for tenant-scoped interviewer feedback."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewRecommendation,
)


class InterviewFeedback(Base):
    """One interviewer's draft or submitted assessment for one session."""

    __tablename__ = "interview_feedback"
    __table_args__ = (
        ForeignKeyConstraint(
            ["interview_session_id", "interviewer_user_id"],
            [
                "interview_participants.interview_session_id",
                "interview_participants.user_id",
            ],
            name="fk_interview_feedback_assigned_participant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "interview_session_id",
            "interviewer_user_id",
            name="uq_interview_feedback_tenant_session_interviewer",
        ),
        CheckConstraint(
            "overall_rating IS NULL OR overall_rating BETWEEN 1 AND 5",
            name="ck_interview_feedback_rating_range",
        ),
        CheckConstraint(
            "(status != 'submitted') OR "
            "(overall_rating IS NOT NULL AND "
            "recommendation IS NOT NULL AND "
            "submitted_at IS NOT NULL)",
            name="ck_interview_feedback_submitted_complete",
        ),
        CheckConstraint(
            "(status = 'submitted') OR submitted_at IS NULL",
            name="ck_interview_feedback_draft_not_submitted",
        ),
        Index(
            "ix_interview_feedback_tenant_session",
            "tenant_id",
            "interview_session_id",
        ),
        Index(
            "ix_interview_feedback_tenant_interviewer_status",
            "tenant_id",
            "interviewer_user_id",
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
    interview_session_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    interviewer_user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    status: Mapped[InterviewFeedbackStatus] = mapped_column(
        Enum(
            InterviewFeedbackStatus,
            name="interview_feedback_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=InterviewFeedbackStatus.DRAFT,
        server_default=InterviewFeedbackStatus.DRAFT.value,
    )
    overall_rating: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    recommendation: Mapped[InterviewRecommendation | None] = mapped_column(
        Enum(
            InterviewRecommendation,
            name="interview_recommendation",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )
    strengths: Mapped[str | None] = mapped_column(Text, nullable=True)
    concerns: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(
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
