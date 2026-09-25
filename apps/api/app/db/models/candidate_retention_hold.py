"""Auditable, tenant-scoped holds that suspend candidate retention review."""

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
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason


class CandidateRetentionHold(Base):
    """One immutable hold record with a single auditable release transition."""

    __tablename__ = "candidate_retention_holds"
    __table_args__ = (
        CheckConstraint(
            "(released_at IS NULL AND released_by_subject IS NULL) OR "
            "(released_at IS NOT NULL AND released_by_subject IS NOT NULL)",
            name="release_metadata_consistent",
        ),
        Index(
            "uq_candidate_retention_hold_one_active_reason",
            "tenant_id",
            "candidate_id",
            "reason",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
        Index(
            "ix_candidate_retention_holds_tenant_candidate_active",
            "tenant_id",
            "candidate_id",
            "released_at",
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
    reason: Mapped[CandidateRetentionHoldReason] = mapped_column(
        Enum(
            CandidateRetentionHoldReason,
            name="candidate_retention_hold_reason",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    released_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}
