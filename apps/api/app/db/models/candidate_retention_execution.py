"""Append-only evidence that a reviewed candidate erasure was executed."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


class CandidateRetentionExecution(Base):
    """Immutable link between a manual-erasure recommendation and its execution."""

    __tablename__ = "candidate_retention_executions"
    __table_args__ = (
        CheckConstraint(
            "review_number >= 1 AND policy_version >= 1",
            name="review_and_policy_versions_positive",
        ),
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            name="uq_candidate_retention_execution_tenant_candidate",
        ),
        UniqueConstraint(
            "tenant_id",
            "review_id",
            name="uq_candidate_retention_execution_tenant_review",
        ),
        Index(
            "ix_candidate_retention_executions_tenant_executed_at",
            "tenant_id",
            "executed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="RESTRICT"), nullable=False
    )
    review_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_retention_reviews.id", ondelete="RESTRICT"),
        nullable=False,
    )
    review_number: Mapped[int] = mapped_column(Integer, nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    executed_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
