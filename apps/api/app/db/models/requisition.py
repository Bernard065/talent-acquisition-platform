"""SQLAlchemy model for job requisitions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.requisitions.enums import RequisitionStatus


class Requisition(Base):
    """
    A tenant-owned request to hire.

    All reads and writes must include tenant_id. The version column supports
    optimistic concurrency checks when recruiters edit the same requisition.
    """

    __tablename__ = "requisitions"
    __table_args__ = (
        Index(
            "ix_requisitions_tenant_status_updated_at",
            "tenant_id",
            "status",
            "updated_at",
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

    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    department: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    headcount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    status: Mapped[RequisitionStatus] = mapped_column(
        Enum(
            RequisitionStatus,
            name="requisition_status",
            values_callable=lambda statuses: [
                status.value for status in statuses
            ],
        ),
        nullable=False,
        default=RequisitionStatus.DRAFT,
        server_default=RequisitionStatus.DRAFT.value,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    created_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __mapper_args__ = {"version_id_col": version}
