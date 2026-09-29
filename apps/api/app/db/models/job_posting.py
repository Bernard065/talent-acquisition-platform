"""SQLAlchemy model for tenant-owned public job postings."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)


class JobPosting(Base):
    """
    A public-facing snapshot of an open requisition.

    `public_id` is globally stable and safe to expose. `slug` is tenant-scoped,
    human-readable, and will be collision-resolved by the workflow service.
    Snapshot fields are populated before publication and preserved thereafter.
    """

    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint(
            "public_id",
            name="uq_job_postings_public_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_job_postings_tenant_slug",
        ),
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_job_postings_tenant_id_id",
        ),
        Index(
            "ix_job_postings_tenant_status_published_at",
            "tenant_id",
            "status",
            "published_at",
        ),
        Index(
            "ix_job_postings_public_status",
            "public_id",
            "status",
        ),
        Index(
            "ix_job_postings_tenant_updated_at_id",
            "tenant_id",
            "updated_at",
            "id",
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
        ForeignKey("requisitions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Stable external identifier. Never derive authorization from this value.
    public_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )
    slug: Mapped[str] = mapped_column(
        String(180),
        nullable=False,
    )

    # Candidate-visible snapshot fields. They must not contain internal notes.
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
    employment_type: Mapped[EmploymentType] = mapped_column(
        Enum(
            EmploymentType,
            name="employment_type",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
    )

    status: Mapped[JobPostingStatus] = mapped_column(
        Enum(
            JobPostingStatus,
            name="job_posting_status",
            values_callable=lambda values: [value.value for value in values],
        ),
        nullable=False,
        default=JobPostingStatus.DRAFT,
        server_default=JobPostingStatus.DRAFT.value,
    )

    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    unpublished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    version: Mapped[int] = mapped_column(
        nullable=False,
        default=1,
    )

    __mapper_args__ = {"version_id_col": version}
