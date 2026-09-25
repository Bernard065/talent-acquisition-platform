"""SQLAlchemy model for tenant-owned candidate profiles."""

from datetime import datetime
from typing import Any
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.enums import (
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)


class Candidate(Base):
    """A tenant-owned candidate profile with a tenant-local identity key."""

    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint(
            "(privacy_status = 'active' AND erasure_requested_at IS NULL "
            "AND erased_at IS NULL) OR "
            "(privacy_status = 'erasure_pending' AND erasure_requested_at IS NOT NULL "
            "AND erased_at IS NULL) OR "
            "(privacy_status = 'erased' AND erasure_requested_at IS NOT NULL "
            "AND erased_at IS NOT NULL)",
            name="privacy_lifecycle_timestamps_consistent",
        ),
        UniqueConstraint(
            "tenant_id",
            "normalized_email",
            name="uq_candidates_tenant_normalized_email",
        ),
        Index(
            "ix_candidates_tenant_created_at",
            "tenant_id",
            "created_at",
        ),
        Index(
            "ix_candidates_tenant_created_at_id",
            "tenant_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_candidates_tenant_privacy_status_created_at",
            "tenant_id",
            "privacy_status",
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

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)

    source: Mapped[str] = mapped_column(String(100), nullable=False)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    consent_status: Mapped[CandidateConsentStatus] = mapped_column(
        Enum(
            CandidateConsentStatus,
            name="candidate_consent_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=CandidateConsentStatus.UNKNOWN,
        server_default=CandidateConsentStatus.UNKNOWN.value,
    )
    consent_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    privacy_status: Mapped[CandidatePrivacyStatus] = mapped_column(
        Enum(
            CandidatePrivacyStatus,
            name="candidate_privacy_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=CandidatePrivacyStatus.ACTIVE,
        server_default=CandidatePrivacyStatus.ACTIVE.value,
    )
    erasure_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    erased_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
