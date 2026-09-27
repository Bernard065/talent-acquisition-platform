"""Candidate processor-disclosure ledger and downstream deletion tracking."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.processor_data import CandidateProcessorDeletionStatus


class CandidateProcessorDisclosure(Base):
    """Minimal evidence that a candidate-linked record reached a processor.

    The external reference is opaque provider metadata needed for a later
    deletion request, not a candidate profile field. It is cleared when
    downstream deletion is confirmed.
    """

    __tablename__ = "candidate_processor_disclosures"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "source_type",
            "source_id",
            name="uq_candidate_processor_disclosures_source",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_candidate_processor_disclosures_tenant_id",
        ),
        CheckConstraint(
            "length(processor_code) BETWEEN 1 AND 100",
            name="ck_candidate_processor_disclosures_processor_code_length",
        ),
        CheckConstraint(
            "length(purpose_code) BETWEEN 1 AND 50",
            name="ck_candidate_processor_disclosures_purpose_code_length",
        ),
        CheckConstraint(
            "purpose_code IN ('interview_scheduling', 'offer_signature', "
            "'onboarding_handoff')",
            name="ck_candidate_processor_disclosures_purpose_code",
        ),
        CheckConstraint(
            "source_type IN ('calendar_sync', 'offer_signature', 'hris_handoff')",
            name="ck_candidate_processor_disclosures_source_type",
        ),
        Index(
            "ix_candidate_processor_disclosures_tenant_candidate",
            "tenant_id",
            "candidate_id",
        ),
        Index(
            "ix_candidate_processor_disclosures_tenant_processor",
            "tenant_id",
            "processor_code",
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
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    processor_code: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose_code: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    external_record_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    disclosed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class CandidateProcessorDeletionRequest(Base):
    """Tenant-scoped work record for deleting one disclosed processor record."""

    __tablename__ = "candidate_processor_deletion_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "disclosure_id"],
            [
                "candidate_processor_disclosures.tenant_id",
                "candidate_processor_disclosures.id",
            ],
            ondelete="RESTRICT",
            name="fk_candidate_processor_deletion_disclosure_tenant",
        ),
        UniqueConstraint(
            "tenant_id",
            "disclosure_id",
            name="uq_candidate_processor_deletion_disclosure",
        ),
        CheckConstraint(
            "status IN ('pending', 'completed', 'exception', 'waived')",
            name="ck_candidate_processor_deletion_requests_status",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_candidate_processor_deletion_requests_version_positive",
        ),
        CheckConstraint(
            "(status = 'pending' AND status_changed_at IS NULL "
            "AND status_changed_by_subject IS NULL AND resolution_code IS NULL) "
            "OR (status = 'completed' AND status_changed_at IS NOT NULL "
            "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NULL) "
            "OR (status IN ('exception', 'waived') AND status_changed_at IS NOT NULL "
            "AND status_changed_by_subject IS NOT NULL AND resolution_code IS NOT NULL)",
            name="ck_candidate_processor_deletion_requests_status_metadata",
        ),
        Index(
            "ix_candidate_processor_deletion_requests_tenant_status_created",
            "tenant_id",
            "status",
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
    )
    disclosure_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=CandidateProcessorDeletionStatus.PENDING,
        server_default=CandidateProcessorDeletionStatus.PENDING.value,
    )
    resolution_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status_changed_by_subject: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}
