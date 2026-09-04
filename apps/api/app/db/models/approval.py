"""SQLAlchemy models for requisition approval policies and decisions."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus


class ApprovalPolicy(Base):
    """A tenant-owned, versioned approval-policy definition."""

    __tablename__ = "approval_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        Index(
            "uq_approval_policies_tenant_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default"),
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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class ApprovalPolicyStep(Base):
    """One sequential named-approver step in an approval policy."""

    __tablename__ = "approval_policy_steps"
    __table_args__ = (
        UniqueConstraint("approval_policy_id", "position"),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    approval_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class RequisitionApproval(Base):
    """Immutable approval-policy snapshot and progress for one submission."""

    __tablename__ = "requisition_approvals"
    __table_args__ = (
        Index(
            "ix_requisition_approvals_tenant_status",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_requisition_approvals_requisition_status",
            "requisition_id",
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
    requisition_id: Mapped[UUID] = mapped_column(
        ForeignKey("requisitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("approval_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    policy_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(
            ApprovalStatus,
            name="approval_status",
            values_callable=lambda statuses: [status.value for status in statuses],
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
        String(255),
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


class RequisitionApprovalDecision(Base):
    """The immutable assignment and eventual decision for one policy step."""

    __tablename__ = "requisition_approval_decisions"
    __table_args__ = (
        UniqueConstraint("requisition_approval_id", "step_position"),
        Index(
            "ix_requisition_approval_decisions_approver_status",
            "approver_user_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    requisition_approval_id: Mapped[UUID] = mapped_column(
        ForeignKey("requisition_approvals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_position: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ApprovalDecisionStatus] = mapped_column(
        Enum(
            ApprovalDecisionStatus,
            name="approval_decision_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ApprovalDecisionStatus.PENDING,
        server_default=ApprovalDecisionStatus.PENDING.value,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
