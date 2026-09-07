"""SQLAlchemy model for immutable candidate document malware scan attempts."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.documents.enums import CandidateDocumentScanStatus


class CandidateDocumentScan(Base):
    """
    One scanner attempt for a candidate document.

    Scanner signatures are retained only for internal security investigation.
    They must never be exposed in candidate-facing or recruiter-facing APIs.
    """

    __tablename__ = "candidate_document_scans"
    __table_args__ = (
        Index(
            "ix_candidate_document_scans_tenant_document_started_at",
            "tenant_id",
            "candidate_document_id",
            "started_at",
        ),
        Index(
            "ix_candidate_document_scans_status_started_at",
            "status",
            "started_at",
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
    candidate_document_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[CandidateDocumentScanStatus] = mapped_column(
        Enum(
            CandidateDocumentScanStatus,
            name="candidate_document_scan_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=CandidateDocumentScanStatus.SCANNING,
        server_default=CandidateDocumentScanStatus.SCANNING.value,
    )
    scanner_name: Mapped[str | None] = mapped_column(String(100))
    detected_signature: Mapped[str | None] = mapped_column(String(500))
    failure_code: Mapped[str | None] = mapped_column(String(100))

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
