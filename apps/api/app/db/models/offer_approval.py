"""Tenant-scoped offer approval persistence."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus


class OfferApproval(Base):
    """An immutable policy snapshot and approval progress for one offer attempt."""

    __tablename__ = "offer_approvals"
    __table_args__ = (
        CheckConstraint(
            "attempt >= 1",
            name="ck_offer_approvals_attempt_positive",
        ),
        CheckConstraint(
            "current_step >= 1",
            name="ck_offer_approvals_current_step_positive",
        ),
        UniqueConstraint(
            "offer_id",
            "attempt",
            name="uq_offer_approvals_offer_attempt",
        ),
        Index(
            "uq_offer_approvals_one_pending_per_offer",
            "offer_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_offer_approvals_tenant_status",
            "tenant_id",
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
    offer_id: Mapped[UUID] = mapped_column(
        ForeignKey("offers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Preserves the policy as it existed at submission time.
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        PostgreSQLEnum(
            ApprovalStatus,
            name="approval_status",
            values_callable=lambda statuses: [status.value for status in statuses],
            create_type=False,
        ),
        nullable=False,
        default=ApprovalStatus.PENDING,
        server_default=ApprovalStatus.PENDING.value,
    )
    current_step: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    submitted_by_subject: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class OfferApprovalDecision(Base):
    """One ordered approver decision within an offer approval attempt."""

    __tablename__ = "offer_approval_decisions"
    __table_args__ = (
        UniqueConstraint(
            "offer_approval_id",
            "step_position",
            name="uq_offer_approval_decisions_step",
        ),
        Index(
            "ix_offer_approval_decisions_approver_status",
            "approver_user_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    offer_approval_id: Mapped[UUID] = mapped_column(
        ForeignKey("offer_approvals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    approver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[ApprovalDecisionStatus] = mapped_column(
        PostgreSQLEnum(
            ApprovalDecisionStatus,
            name="approval_decision_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ApprovalDecisionStatus.PENDING,
        server_default=ApprovalDecisionStatus.PENDING.value,
    )
    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
