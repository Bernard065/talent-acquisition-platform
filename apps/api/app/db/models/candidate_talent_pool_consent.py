"""Append-only evidence for purpose-specific future-opportunity consent."""

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
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)


class CandidateTalentPoolConsentEvent(Base):
    """One immutable grant, renewal, or withdrawal with provenance metadata."""

    __tablename__ = "candidate_talent_pool_consent_events"
    __table_args__ = (
        CheckConstraint(
            "(event_type = 'withdrawn' OR notice_version IS NOT NULL) AND "
            "(capture_method <> 'erasure_request' OR event_type = 'withdrawn')",
            name="consent_provenance_consistent",
        ),
        CheckConstraint("event_version >= 1", name="event_version_positive"),
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "event_version",
            name="uq_candidate_talent_pool_consent_version",
        ),
        Index(
            "ix_candidate_talent_pool_consent_latest",
            "tenant_id",
            "candidate_id",
            text("event_version DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False
    )
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[CandidateTalentPoolConsentEventType] = mapped_column(
        Enum(
            CandidateTalentPoolConsentEventType,
            name="candidate_talent_pool_consent_event_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    capture_method: Mapped[CandidateTalentPoolCaptureMethod] = mapped_column(
        Enum(
            CandidateTalentPoolCaptureMethod,
            name="candidate_talent_pool_capture_method",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    notice_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recorded_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
