"""Strict anonymous response contracts for public job discovery."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.job_postings.enums import EmploymentType


class PublicJobSummaryResponse(BaseModel):
    """Candidate-safe metadata for a public job-search result."""

    model_config = ConfigDict(from_attributes=True)

    public_id: UUID
    slug: str
    title: str
    department: str | None
    location: str | None
    employment_type: EmploymentType
    published_at: datetime
    expires_at: datetime | None


class PublicJobDetailResponse(PublicJobSummaryResponse):
    """Candidate-safe detail for one currently visible public job."""

    description: str | None


class PublicJobListResponse(BaseModel):
    """Cursor-paginated collection of public job-search results."""

    model_config = ConfigDict(extra="forbid")

    items: list[PublicJobSummaryResponse]
    next_cursor: str | None = None
