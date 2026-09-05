"""SQLAlchemy model for candidate applications to job requisitions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.enums import ApplicationStatus


class Application(Base):
    """A candidate's tenant-scoped application to one requisition."""

    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "requisition_id",
            name="uq_applications_tenant_candidate_requisition",
        ),
        Index(
            "ix_applications_tenant_requisition_status_applied_at",
            "tenant_id",
            "requisition_id",
            "status",
            "applied_at",
        ),
        Index(
            "ix_applications_tenant_candidate_id",
            "tenant_id",
            "candidate_id",
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
    candidate_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    requisition_id: Mapped[UUID] = mapped_column(
        ForeignKey("requisitions.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(
            ApplicationStatus,
            name="application_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=ApplicationStatus.APPLIED,
        server_default=ApplicationStatus.APPLIED.value,
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
