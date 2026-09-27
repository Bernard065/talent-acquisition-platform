"""Tenant-scoped persistence for application debrief decisions."""

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
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.enums import ApplicationRejectionReason
from app.domains.decisions.enums import HiringDecision


class ApplicationDebrief(Base):
    """One final, tenant-scoped decision record for an application."""

    __tablename__ = "application_debriefs"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "application_id",
            name="uq_application_debriefs_tenant_application",
        ),
        CheckConstraint(
            "char_length(rationale) BETWEEN 1 AND 5000",
            name="ck_application_debriefs_rationale_length",
        ),
        CheckConstraint(
            "(decision != 'reject') OR rejection_reason IS NOT NULL",
            name="ck_application_debriefs_rejection_reason_required",
        ),
        CheckConstraint(
            "(decision = 'reject') OR rejection_reason IS NULL",
            name="ck_application_debriefs_rejection_reason_only_for_reject",
        ),
        Index(
            "ix_application_debriefs_tenant_application",
            "tenant_id",
            "application_id",
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
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    decision: Mapped[HiringDecision] = mapped_column(
        Enum(
            HiringDecision,
            name="hiring_decision",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    rejection_reason: Mapped[ApplicationRejectionReason | None] = mapped_column(
        Enum(
            ApplicationRejectionReason,
            name="application_rejection_reason",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=True,
    )

    decided_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
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
    )

    __mapper_args__ = {"version_id_col": version}


class ApplicationDecisionHistory(Base):
    """Immutable audit-grade history for a debrief decision."""

    __tablename__ = "application_decision_history"
    __table_args__ = (
        Index(
            "ix_application_decision_history_tenant_application_decided_at",
            "tenant_id",
            "application_id",
            "decided_at",
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
    application_id: Mapped[UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    application_debrief_id: Mapped[UUID] = mapped_column(
        ForeignKey("application_debriefs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    decision: Mapped[HiringDecision] = mapped_column(
        PostgreSQLEnum(
            HiringDecision,
            name="hiring_decision",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=False,
    )
    rejection_reason: Mapped[ApplicationRejectionReason | None] = mapped_column(
        PostgreSQLEnum(
            ApplicationRejectionReason,
            name="application_rejection_reason",
            values_callable=lambda values: [value.value for value in values],
            create_type=False,
        ),
        nullable=True,
    )
    decided_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
