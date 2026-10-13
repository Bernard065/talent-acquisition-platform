"""HTTP contracts for recruiter screening assessments."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.applications.screening import ScreeningRecommendation


class ScreeningCriterionRequest(BaseModel):
    """A configured rubric criterion and the reviewer's assessment of it."""

    model_config = ConfigDict(extra="forbid")

    criterion_id: UUID
    rating: int = Field(ge=1, le=5)
    evidence: str | None = Field(default=None, max_length=2000)


class ScreeningRubricCriterion(BaseModel):
    """One shared, job-specific criterion used by every reviewer."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: UUID
    criterion: str = Field(min_length=1, max_length=200)
    guidance: str | None = Field(default=None, max_length=1000)


class ScreeningRubricResponse(BaseModel):
    """Current screening rubric for one job posting."""

    model_config = ConfigDict(extra="forbid")

    items: list[ScreeningRubricCriterion]
    version: int = Field(ge=1)


class ReplaceScreeningRubricRequest(BaseModel):
    """Replace a job's shared screening rubric optimistically."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    items: list[ScreeningRubricCriterion] = Field(max_length=10)

    @model_validator(mode="after")
    def validate_unique_criteria(self) -> "ReplaceScreeningRubricRequest":
        ids = [item.id for item in self.items]
        labels = [item.criterion.casefold() for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Rubric criterion IDs must be unique.")
        if len(labels) != len(set(labels)):
            raise ValueError("Rubric criteria must be unique.")
        return self


class ApplicationScreeningAssessmentCreateRequest(BaseModel):
    """A complete screening scorecard submitted by a recruiter."""

    model_config = ConfigDict(extra="forbid")

    overall_rating: int = Field(ge=1, le=5)
    recommendation: ScreeningRecommendation
    rubric_version: int = Field(ge=1)
    criteria: list[ScreeningCriterionRequest] = Field(min_length=1, max_length=10)
    summary: str = Field(min_length=1, max_length=5000)


class ScreeningCriterionResponse(BaseModel):
    """One persisted requirement score and evidence note."""

    criterion_id: UUID | None = None
    criterion: str
    guidance: str | None = None
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
    rubric_version: int | None = None
    submitted_at: datetime


class ApplicationScreeningAssessmentListResponse(BaseModel):
    """Submitted screening assessments for one application."""

    items: list[ApplicationScreeningAssessmentResponse]
    my_assessment_id: UUID | None
    rubric: list[ScreeningRubricCriterion] = Field(default_factory=list)
    rubric_version: int | None = None
