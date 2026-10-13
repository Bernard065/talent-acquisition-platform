"""Request and response schemas for job-application endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.applications.screening import ApplicationScreeningProgress
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
    follow_up_action: str | None
    follow_up_due_at: datetime | None
    status: ApplicationStatus
    applied_at: datetime
    version: int
    screening_progress: ApplicationScreeningProgress


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
    follow_up_count: int
    overdue_follow_up_count: int


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


class ApplicationFollowUpCreateRequest(BaseModel):
    """Create a next action and due date for an application."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(min_length=1, max_length=500)
    due_at: datetime


class ApplicationFollowUpUpdateRequest(ApplicationFollowUpCreateRequest):
    """Update a pending follow-up using optimistic concurrency."""

    expected_version: int = Field(ge=1)


class ApplicationFollowUpCompleteRequest(BaseModel):
    """Complete a pending follow-up using optimistic concurrency."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ApplicationFollowUpResponse(BaseModel):
    """Follow-up history item for an application profile."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    action: str
    due_at: datetime
    created_at: datetime
    completed_at: datetime | None
    version: int


class ApplicationFollowUpListResponse(BaseModel):
    """Follow-up history with the active action identified explicitly."""

    items: list[ApplicationFollowUpResponse]
    active_follow_up_id: UUID | None
