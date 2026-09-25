"""Immutable candidate-level evidence from a human retention review."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
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
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewPurpose,
    CandidateRetentionReviewReason,
)


class CandidateRetentionReview(Base):
    """An append-only review record; it never triggers or performs erasure."""

    __tablename__ = "candidate_retention_reviews"
    __table_args__ = (
        CheckConstraint(
            "review_number >= 1 AND policy_version >= 1",
            name="review_number_and_policy_version_positive",
        ),
        CheckConstraint(
            "unsuccessful_applicant_days BETWEEN 1 AND 3650 AND "
            "withdrawn_applicant_days BETWEEN 1 AND 3650 AND "
            "talent_pool_days BETWEEN 1 AND 3650 AND "
            "hired_recruiting_copy_days BETWEEN 1 AND 3650",
            name="policy_snapshot_intervals_valid",
        ),
        CheckConstraint(
            "(disposition = 'recommend_manual_erasure' AND "
            "reason_code = 'review_complete' AND next_review_at IS NULL AND "
            "active_matters_reviewed AND legal_holds_reviewed AND "
            "other_lawful_basis_reviewed AND employee_obligations_reviewed AND "
            "external_processors_reviewed AND backup_restore_safeguards_reviewed) OR "
            "(disposition IN ('retain', 'defer') AND "
            "reason_code <> 'review_complete' AND next_review_at IS NOT NULL)",
            name="review_disposition_consistent",
        ),
        CheckConstraint(
            "next_review_at IS NULL OR next_review_at > reviewed_at",
            name="next_review_after_reviewed_at",
        ),
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "review_number",
            name="uq_candidate_retention_review_tenant_candidate_number",
        ),
        Index(
            "ix_candidate_retention_reviews_tenant_candidate_number",
            "tenant_id",
            "candidate_id",
            text("review_number DESC"),
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
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_retention_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    unsuccessful_applicant_days: Mapped[int] = mapped_column(Integer, nullable=False)
    withdrawn_applicant_days: Mapped[int] = mapped_column(Integer, nullable=False)
    talent_pool_days: Mapped[int] = mapped_column(Integer, nullable=False)
    hired_recruiting_copy_days: Mapped[int] = mapped_column(Integer, nullable=False)
    review_number: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[CandidateRetentionReviewPurpose] = mapped_column(
        Enum(
            CandidateRetentionReviewPurpose,
            name="candidate_retention_review_purpose",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    disposition: Mapped[CandidateRetentionReviewDisposition] = mapped_column(
        Enum(
            CandidateRetentionReviewDisposition,
            name="candidate_retention_review_disposition",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    reason_code: Mapped[CandidateRetentionReviewReason] = mapped_column(
        Enum(
            CandidateRetentionReviewReason,
            name="candidate_retention_review_reason",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    active_matters_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    legal_holds_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    other_lawful_basis_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    employee_obligations_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    external_processors_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    backup_restore_safeguards_reviewed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )
    reviewed_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    next_review_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
