"""Private API contracts for recruiting analytics."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.domains.candidates.enums import ApplicationStatus


class FunnelMetricResponse(BaseModel):
    """One aggregate pipeline-stage entry count."""

    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus
    count: int = Field(ge=0)


class StageTransitionMetricResponse(BaseModel):
    """One aggregate application-stage transition count."""

    model_config = ConfigDict(extra="forbid")

    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    count: int = Field(ge=0)


class SourceEffectivenessMetricResponse(BaseModel):
    """Aggregate outcomes for one non-PII candidate source."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=100)
    application_count: int = Field(ge=0)
    hired_count: int = Field(ge=0)


class TimeToHireMetricResponse(BaseModel):
    """Aggregate time from application submission to hiring."""

    model_config = ConfigDict(extra="forbid")

    hired_count: int = Field(ge=0)
    average_hours: float | None = Field(default=None, ge=0)


class RecruitingMetricsResponse(BaseModel):
    """Tenant-private aggregate recruiting analytics."""

    model_config = ConfigDict(extra="forbid")

    starts_at: datetime
    ends_at: datetime
    funnel: list[FunnelMetricResponse]
    stage_transitions: list[StageTransitionMetricResponse]
    source_effectiveness: list[SourceEffectivenessMetricResponse]
    time_to_hire: TimeToHireMetricResponse

    @field_serializer("starts_at", "ends_at")
    def serialize_timestamp(self, value: datetime) -> str:
        """Preserve the explicit UTC offset in analytics timestamps."""
        return value.isoformat()
