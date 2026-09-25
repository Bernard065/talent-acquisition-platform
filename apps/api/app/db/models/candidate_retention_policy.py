"""Versioned, tenant-owned candidate retention schedules."""

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
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus


class CandidateRetentionPolicy(Base):
    """Versioned schedules; activation retires the prior version, not its history."""

    __tablename__ = "candidate_retention_policies"
    __table_args__ = (
        CheckConstraint("policy_version >= 1", name="policy_version_positive"),
        CheckConstraint(
            "unsuccessful_applicant_days BETWEEN 1 AND 3650", name="unsuccessful_days_valid"
        ),
        CheckConstraint("withdrawn_applicant_days BETWEEN 1 AND 3650", name="withdrawn_days_valid"),
        CheckConstraint("talent_pool_days BETWEEN 1 AND 3650", name="talent_pool_days_valid"),
        CheckConstraint(
            "hired_recruiting_copy_days BETWEEN 1 AND 3650", name="hired_copy_days_valid"
        ),
        CheckConstraint(
            "(status = 'draft' AND activated_at IS NULL AND activated_by_subject IS NULL) "
            "OR (status IN ('active', 'retired') AND activated_at IS NOT NULL "
            "AND activated_by_subject IS NOT NULL)",
            name="activation_metadata_consistent",
        ),
        UniqueConstraint(
            "tenant_id", "policy_version", name="uq_candidate_retention_policy_tenant_version"
        ),
        Index(
            "uq_candidate_retention_policy_one_active_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_candidate_retention_policy_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CandidateRetentionPolicyStatus] = mapped_column(
        Enum(
            CandidateRetentionPolicyStatus,
            name="candidate_retention_policy_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=CandidateRetentionPolicyStatus.DRAFT,
        server_default=CandidateRetentionPolicyStatus.DRAFT.value,
    )
    unsuccessful_applicant_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default="365"
    )
    withdrawn_applicant_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default="365"
    )
    talent_pool_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=365, server_default="365"
    )
    hired_recruiting_copy_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90, server_default="90"
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    activated_by_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": row_version}
