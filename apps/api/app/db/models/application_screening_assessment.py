"""Immutable recruiter screening assessments for job applications."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.applications.screening import ScreeningRecommendation


class ApplicationScreeningAssessment(Base):
    """One submitted assessment per reviewer and tenant application."""

    __tablename__ = "application_screening_assessments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            "reviewer_user_id",
            name="uq_application_screening_assessments_reviewer",
        ),
        CheckConstraint(
            "overall_rating BETWEEN 1 AND 5",
            name="rating_range",
        ),
        CheckConstraint(
            "recommendation in ('advance', 'hold', 'reject')",
            name="recommendation",
        ),
        CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 5000",
            name="summary_length",
        ),
        Index(
            "ix_screening_assessments_tenant_app_submitted",
            "tenant_id",
            "application_id",
            "submitted_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    overall_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation: Mapped[ScreeningRecommendation] = mapped_column(
        Enum(
            ScreeningRecommendation,
            name="screening_recommendation",
            native_enum=False,
            length=16,
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_version: Mapped[int | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
