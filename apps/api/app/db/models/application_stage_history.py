"""Immutable history of application pipeline stage transitions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import ENUM as PostgreSQLEnum
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)


class ApplicationStageHistory(Base):
    """
    One immutable application-stage transition.

    Database migrations enforce append-only behavior. Rejection reasons are
    populated later by the transition service only for rejected applications.
    """

    __tablename__ = "application_stage_history"
    __table_args__ = (
        Index(
            "ix_application_stage_history_tenant_application_transitioned_at",
            "tenant_id",
            "application_id",
            "transitioned_at",
        ),
        Index(
            "ix_application_stage_history_tenant_transitioned_at_to_status",
            "tenant_id",
            "transitioned_at",
            "to_status",
        ),
        Index(
            "ix_application_stage_history_tenant_to_status_transitioned_at",
            "tenant_id",
            "to_status",
            "transitioned_at",
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

    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        PostgreSQLEnum(
            ApplicationStatus,
            name="application_status",
            values_callable=lambda statuses: [status.value for status in statuses],
            create_type=False,
        ),
        nullable=True,
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        PostgreSQLEnum(
            ApplicationStatus,
            name="application_status",
            values_callable=lambda statuses: [status.value for status in statuses],
            create_type=False,
        ),
        nullable=False,
    )
    rejection_reason: Mapped[ApplicationRejectionReason | None] = mapped_column(
        PostgreSQLEnum(
            ApplicationRejectionReason,
            name="application_rejection_reason",
            values_callable=lambda reasons: [reason.value for reason in reasons],
            create_type=False,
        ),
        nullable=True,
    )

    transitioned_by_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
