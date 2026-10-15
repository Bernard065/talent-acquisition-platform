"""Strict HTTP contracts for interview scheduling."""

from datetime import datetime
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
    InterviewCalendarSyncStatus,
)
from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewFormat,
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
    format: InterviewFormat | None = None
    meeting_url: AnyHttpUrl | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    participants: list[InterviewParticipantRequest] = Field(
        min_length=1,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_format_details(self) -> "ScheduleInterviewRequest":
        """Require a meeting link online or a venue for in-person sessions."""
        location = self.location.strip() if self.location else None
        if self.format is InterviewFormat.ONLINE:
            if self.meeting_url is None:
                raise ValueError("An online interview requires a meeting URL.")
            if location:
                raise ValueError("An online interview cannot include an in-person location.")
        elif self.format is InterviewFormat.IN_PERSON:
            if self.meeting_url is not None:
                raise ValueError("An in-person interview cannot include a meeting URL.")
            if not location:
                raise ValueError("An in-person interview requires a location.")
        elif self.meeting_url is not None or location:
            raise ValueError("Set the interview format before providing location details.")
        self.location = location
        return self


class InterviewSessionResponse(BaseModel):
    """Safe metadata for a tenant-owned interview session."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    format: InterviewFormat | None = None
    meeting_url: str | None = None
    location: str | None = None
    status: InterviewSessionStatus
    completed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: InterviewCancellationReason | None
    created_at: datetime
    updated_at: datetime
    version: int


class InterviewCalendarSyncResponse(BaseModel):
    """Safe calendar delivery state for one interview participant calendar."""

    model_config = ConfigDict(extra="forbid")

    calendar_owner_display_name: str
    provider: CalendarProvider
    connection_status: CalendarConnectionStatus
    status: InterviewCalendarSyncStatus
    last_error_code: str | None
    last_attempt_at: datetime | None
    synced_at: datetime | None


class InterviewCalendarSyncListResponse(BaseModel):
    """Calendar synchronization states associated with one interview."""

    model_config = ConfigDict(extra="forbid")

    items: list[InterviewCalendarSyncResponse]
    can_retry: bool


class InterviewCalendarSyncRetryResponse(BaseModel):
    """Acknowledgement that failed calendar delivery was queued for retry."""

    model_config = ConfigDict(extra="forbid")

    status: str = "queued"


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
