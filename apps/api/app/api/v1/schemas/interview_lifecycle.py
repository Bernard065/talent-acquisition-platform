"""Strict HTTP contracts for interview session lifecycle operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.interviews.enums import InterviewCancellationReason


class CompleteInterviewSessionRequest(BaseModel):
    """Input for completing one versioned interview session."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class CancelInterviewSessionRequest(BaseModel):
    """Input for cancelling one versioned interview session."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    cancellation_reason: InterviewCancellationReason


class RescheduleInterviewSessionRequest(BaseModel):
    """Input for moving one versioned interview session."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    scheduled_start_at: datetime
    scheduled_end_at: datetime
