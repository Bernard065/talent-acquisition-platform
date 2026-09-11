"""Strict HTTP contracts for interview scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewParticipantRole,
    InterviewSessionStatus,
)


class InterviewParticipantRequest(BaseModel):
    """One internal participant reserved for the interview."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: InterviewParticipantRole


class ScheduleInterviewRequest(BaseModel):
    """Input for scheduling a tenant-owned application interview."""

    model_config = ConfigDict(extra="forbid")

    scheduled_start_at: datetime
    scheduled_end_at: datetime
    participants: list[InterviewParticipantRequest] = Field(
        min_length=1,
        max_length=20,
    )


class InterviewSessionResponse(BaseModel):
    """Safe metadata for a tenant-owned interview session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    status: InterviewSessionStatus
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: InterviewCancellationReason | None
    created_at: datetime
    updated_at: datetime
    version: int


class InterviewParticipantSummaryResponse(BaseModel):
    """Participant identity metadata safe for tenant interview calendars."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    role: InterviewParticipantRole


class InterviewSearchResultResponse(InterviewSessionResponse):
    """Calendar-safe interview session details without feedback content."""

    participants: list[InterviewParticipantSummaryResponse]


class InterviewSearchListResponse(BaseModel):
    """Cursor-paginated tenant interview schedule search results."""

    model_config = ConfigDict(extra="forbid")

    items: list[InterviewSearchResultResponse]
    next_cursor: str | None = None
