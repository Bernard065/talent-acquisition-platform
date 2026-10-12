"""HTTP contracts for recruiter screening assessments."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.applications.screening import ScreeningRecommendation


class ScreeningCriterionRequest(BaseModel):
    """A job requirement and the recruiter's evidence-based assessment of it."""

    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1, max_length=200)
    rating: int = Field(ge=1, le=5)
    evidence: str | None = Field(default=None, max_length=2000)


class ApplicationScreeningAssessmentCreateRequest(BaseModel):
    """A complete screening scorecard submitted by a recruiter."""

    model_config = ConfigDict(extra="forbid")

    overall_rating: int = Field(ge=1, le=5)
    recommendation: ScreeningRecommendation
    criteria: list[ScreeningCriterionRequest] = Field(min_length=1, max_length=10)
    summary: str = Field(min_length=1, max_length=5000)


class ScreeningCriterionResponse(BaseModel):
    """One persisted requirement score and evidence note."""

    criterion: str
    rating: int
    evidence: str | None


class ApplicationScreeningAssessmentResponse(BaseModel):
    """A submitted scorecard visible to recruiting roles in the tenant."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    reviewer_display_name: str
    overall_rating: int
    recommendation: ScreeningRecommendation
    criteria: list[ScreeningCriterionResponse]
    summary: str
    submitted_at: datetime


class ApplicationScreeningAssessmentListResponse(BaseModel):
    """Submitted screening assessments for one application."""

    items: list[ApplicationScreeningAssessmentResponse]
    my_assessment_id: UUID | None
