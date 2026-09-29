"""Persistence model for publishing a local posting to an external job board."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.job_boards.enums import JobBoardPublicationStatus


class JobBoardPublication(Base):
    """Tenant-owned synchronization state for one posting/provider pair.

    Provider credentials are deliberately not stored here. The future provider
    adapter resolves credentials from the configured external secret vault.
    """

    __tablename__ = "job_board_publications"
    __table_args__ = (
        CheckConstraint(
            "provider_key ~ '^[a-z][a-z0-9_-]{0,63}$'",
            name="provider_key_format",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR "
            "last_error_code ~ '^[a-z0-9][a-z0-9_.-]{0,99}$'",
            name="safe_error_code",
        ),
        CheckConstraint(
            "(dispatch_locked_by IS NULL) = (dispatch_locked_until IS NULL)",
            name="dispatch_lease_consistent",
        ),
        UniqueConstraint(
            "tenant_id",
            "job_posting_id",
            "provider_key",
            name="uq_job_board_publications_tenant_posting_provider",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_posting_id"],
            ["job_postings.tenant_id", "job_postings.id"],
            name="fk_job_board_publications_tenant_posting",
            ondelete="CASCADE",
        ),
        Index(
            "ix_job_board_publications_tenant_status_updated_at",
            "tenant_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_job_board_publications_provider_status_updated_at",
            "provider_key",
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
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    job_posting_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
    )
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobBoardPublicationStatus] = mapped_column(
        Enum(
            JobBoardPublicationStatus,
            name="job_board_publication_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        nullable=False,
        default=JobBoardPublicationStatus.PUBLISH_REQUESTED,
        server_default=JobBoardPublicationStatus.PUBLISH_REQUESTED.value,
    )
    # Desired-state generation changes only when a new publish/unpublish intent
    # is committed. Worker result persistence can safely increment `version`
    # without invalidating an already queued newer intent.
    desired_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )
    # Highest generation confirmed at the provider. Older retried events can
    # be acknowledged once a newer desired state has already been synchronized.
    last_synced_generation: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    external_posting_id: Mapped[str | None] = mapped_column(String(255))
    last_error_code: Mapped[str | None] = mapped_column(String(100))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_locked_by: Mapped[str | None] = mapped_column(String(255))
    dispatch_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_by_subject: Mapped[str] = mapped_column(String(255), nullable=False)
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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    __mapper_args__ = {"version_id_col": version}
