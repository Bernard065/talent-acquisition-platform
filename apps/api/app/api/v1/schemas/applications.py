"""Request and response schemas for job-application endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domains.candidates.enums import ApplicationStatus


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
    status: ApplicationStatus
    applied_at: datetime
    created_at: datetime
    updated_at: datetime
    version: int


class ApplicationListResponse(BaseModel):
    """Cursor-paginated internal application search results."""

    model_config = ConfigDict(extra="forbid")

    items: list[ApplicationResponse]
    next_cursor: str | None = None
