"""Request and response schemas for job-application endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)


class ApplicationCreateRequest(BaseModel):
    """Input for connecting a candidate to an open requisition."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: UUID
    requisition_id: UUID


class ApplicationResponse(BaseModel):
    """Tenant-scoped representation of a candidate job application."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_id: UUID
    requisition_id: UUID
    assigned_to_user_id: UUID | None = None
    status: ApplicationStatus
    applied_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int


class ApplicationActivityItemResponse(BaseModel):
    """One immutable pipeline-stage event for an application timeline."""

    id: UUID
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    rejection_reason: ApplicationRejectionReason | None
    actor_display_name: str
    transitioned_at: datetime


class ApplicationActivityResponse(BaseModel):
    """Stage-transition activity for one application, newest first."""

    items: list[ApplicationActivityItemResponse]


class ApplicationListResponse(BaseModel):
    """Cursor-paginated internal application search results."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationResponse]
    next_cursor: str | None = None


class ApplicationPipelineItemResponse(BaseModel):
    """Recruiter-safe summary used to render an application pipeline card."""

    id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str | None
    requisition_id: UUID
    requisition_title: str
    assigned_to_user_id: UUID | None
    assigned_to_display_name: str | None
    status: ApplicationStatus
    applied_at: datetime
    version: int


class ApplicationPipelineListResponse(BaseModel):
    """Cursor-paginated application summaries for the recruiter pipeline."""

    items: list[ApplicationPipelineItemResponse]
    next_cursor: str | None = None
    stage_counts: dict[ApplicationStatus, int]


class ApplicationPipelineJobSummaryResponse(BaseModel):
    """Application counts for one job, grouped by the current pipeline stage."""

    requisition_id: UUID
    requisition_title: str
    total_count: int
    stage_counts: dict[ApplicationStatus, int]


class ApplicationPipelineSummaryResponse(BaseModel):
    """Filtered application totals without loading candidate profile data."""

    total_count: int
    stage_counts: dict[ApplicationStatus, int]
    jobs: list[ApplicationPipelineJobSummaryResponse]


class ApplicationAssignmentRequest(BaseModel):
    """Set or clear the recruiter responsible for an application."""

    model_config = ConfigDict(extra="forbid")

    assigned_to_user_id: UUID | None
    expected_version: int = Field(ge=1)
