"""Strict HTTP contracts for private onboarding workflow operations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.authorization import Role
from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskStatus,
)


class OnboardingTemplateTaskRequest(BaseModel):
    """One ordered onboarding task definition."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_offset_days: int | None = Field(default=None, ge=0)
    default_assignee_role: Role | None = None


class CreateOnboardingTemplateRequest(BaseModel):
    """Input for a tenant-owned onboarding template version."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    version: int = Field(default=1, ge=1)
    tasks: list[OnboardingTemplateTaskRequest] = Field(
        min_length=1,
        max_length=100,
    )


class StartOnboardingRequest(BaseModel):
    """Input for starting onboarding for a hired application."""

    model_config = ConfigDict(extra="forbid")

    onboarding_template_id: UUID


class AssignOnboardingTaskRequest(BaseModel):
    """Input for assigning an onboarding task."""

    model_config = ConfigDict(extra="forbid")

    assignee_user_id: UUID
    expected_task_version: int = Field(ge=1)


class UpdateOnboardingTaskStatusRequest(BaseModel):
    """Input for one optimistic-concurrency task status transition."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target_status: OnboardingTaskStatus
    blocked_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_blocked_reason(
        self,
    ) -> "UpdateOnboardingTaskStatusRequest":
        """Require a reason only when a task is blocked."""
        normalized_reason = (
            self.blocked_reason.strip()
            if self.blocked_reason is not None
            else None
        )

        if self.target_status is OnboardingTaskStatus.BLOCKED:
            if not normalized_reason:
                raise ValueError(
                    "blocked_reason is required when target_status is blocked."
                )
        elif normalized_reason is not None:
            raise ValueError(
                "blocked_reason is allowed only when target_status is blocked."
            )

        self.blocked_reason = normalized_reason
        return self


class ExpectedInstanceVersionRequest(BaseModel):
    """Concurrency precondition for an onboarding-instance mutation."""

    model_config = ConfigDict(extra="forbid")

    expected_instance_version: int = Field(ge=1)


class OnboardingTemplateResponse(BaseModel):
    """Safe metadata for a created onboarding template."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int
    is_active: bool
    created_at: datetime


class OnboardingInstanceResponse(BaseModel):
    """Private onboarding instance metadata without applicant PII."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    onboarding_template_id: UUID
    status: OnboardingInstanceStatus
    started_at: datetime
    completed_at: datetime | None
    cancelled_at: datetime | None
    version: int


class OnboardingTaskResponse(BaseModel):
    """Private operational data for one onboarding task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    onboarding_instance_id: UUID
    template_task_id: UUID
    title: str
    description: str | None
    due_at: datetime | None
    assignee_user_id: UUID | None
    status: OnboardingTaskStatus
    completed_at: datetime | None
    blocked_reason: str | None
    version: int
