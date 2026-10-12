"""Strict HTTP contracts for interviewer feedback."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewRecommendation,
)


class InterviewFeedbackDraftRequest(BaseModel):
    """Optional initial content for one interviewer feedback draft."""

    model_config = ConfigDict(extra="forbid")

    overall_rating: int | None = Field(default=None, ge=1, le=5)
    recommendation: InterviewRecommendation | None = None
    strengths: str | None = Field(default=None, max_length=5000)
    concerns: str | None = Field(default=None, max_length=5000)


class InterviewFeedbackDraftUpdateRequest(BaseModel):
    """Full replacement content for one versioned feedback draft."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    overall_rating: int | None = Field(default=None, ge=1, le=5)
    recommendation: InterviewRecommendation | None = None
    strengths: str | None = Field(default=None, max_length=5000)
    concerns: str | None = Field(default=None, max_length=5000)


class InterviewFeedbackSubmitRequest(BaseModel):
    """Required final content for feedback submission."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    overall_rating: int = Field(ge=1, le=5)
    recommendation: InterviewRecommendation
    strengths: str | None = Field(default=None, max_length=5000)
    concerns: str | None = Field(default=None, max_length=5000)


class InterviewFeedbackResponse(BaseModel):
    """Private feedback representation visible only to its author."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interview_session_id: UUID
    status: InterviewFeedbackStatus
    overall_rating: int | None
    recommendation: InterviewRecommendation | None
    strengths: str | None
    concerns: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version: int


class MyInterviewFeedbackResponse(BaseModel):
    """Only the caller's feedback for an assigned interview session."""

    feedback: InterviewFeedbackResponse | None


class ApplicationInterviewFeedbackItemResponse(BaseModel):
    """Submitted interviewer assessment visible to recruiting decision makers."""

    id: UUID
    interview_session_id: UUID
    scheduled_start_at: datetime
    interviewer_display_name: str
    status: InterviewFeedbackStatus
    overall_rating: int
    recommendation: InterviewRecommendation
    strengths: str | None
    concerns: str | None
    submitted_at: datetime


class ApplicationInterviewFeedbackListResponse(BaseModel):
    """Submitted assessments for one application, excluding private drafts."""

    items: list[ApplicationInterviewFeedbackItemResponse]
