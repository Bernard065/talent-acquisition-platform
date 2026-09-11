"""Private API contracts for job-posting management."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class CreateJobPostingRequest(BaseModel):
    """Validated input for creating a draft posting from a requisition."""

    model_config = ConfigDict(extra="forbid")

    employment_type: EmploymentType
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self) -> Self:
        """Require an explicit UTC offset when an expiry is supplied."""
        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("expires_at must include a UTC offset.")

        return self


class ExpectedJobPostingVersionRequest(BaseModel):
    """Optimistic-concurrency input for a job-posting state change."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
