"""Private API contracts for job-posting management."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.job_postings.enums import EmploymentType, JobPostingStatus


class JobPostingResponse(BaseModel):
    """Safe tenant-private representation of a job posting."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    requisition_id: UUID
    public_id: UUID
    slug: str
    title: str = Field(max_length=200)
    description: str
    department: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    employment_type: EmploymentType
    status: JobPostingStatus
    published_at: datetime | None
    unpublished_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int = Field(ge=1)


class JobPostingListResponse(BaseModel):
    """Cursor-paginated tenant-private job-posting list."""

    model_config = ConfigDict(extra="forbid")

    items: list[JobPostingResponse]
    next_cursor: str | None
