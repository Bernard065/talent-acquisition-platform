"""Strict HTTP contracts for private onboarding workflow operations."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.v1.schemas.employee_records import EmployeePortalProfileResponse
from app.core.authorization import Role
from app.domains.onboarding.enums import (
    OnboardingInstanceStatus,
    OnboardingTaskDocumentStatus,
    OnboardingTaskEventType,
    OnboardingTaskResponsibility,
    OnboardingTaskStatus,
    OnboardingTaskWorklistView,
)


class OnboardingTemplateTaskRequest(BaseModel):
    """One ordered onboarding task definition."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    due_offset_days: int | None = Field(default=None, ge=0)
    default_assignee_role: Role | None = None
    responsible_party: OnboardingTaskResponsibility = (
        OnboardingTaskResponsibility.WORKSPACE
    )
    requires_document_upload: bool = False

    @model_validator(mode="after")
    def validate_responsible_party(self) -> "OnboardingTemplateTaskRequest":
        """Employee-owned tasks cannot have a workspace role assignee."""
        if (
            self.responsible_party is OnboardingTaskResponsibility.EMPLOYEE
            and self.default_assignee_role is not None
        ):
            raise ValueError(
                "Employee-owned tasks cannot have a default workspace assignee role."
            )
        if (
            self.requires_document_upload
            and self.responsible_party is not OnboardingTaskResponsibility.EMPLOYEE
        ):
            raise ValueError("Only employee-owned tasks can request file uploads.")
        return self


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
    """Input for assigning or unassigning an onboarding task."""

    model_config = ConfigDict(extra="forbid")

    assignee_user_id: UUID | None
    expected_task_version: int = Field(ge=1)


class UpdateOnboardingTaskDueDateRequest(BaseModel):
    """Input for changing or clearing an onboarding task's due date."""

    model_config = ConfigDict(extra="forbid")

    due_date: date | None
    expected_task_version: int = Field(ge=1)


class UpdateOnboardingTaskStatusRequest(BaseModel):
    """Input for one optimistic-concurrency task status transition."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target_status: OnboardingTaskStatus
    blocked_reason: str | None = Field(default=None, max_length=2000)
    resolution_note: str | None = Field(default=None, max_length=2000)

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
        normalized_resolution_note = (
            self.resolution_note.strip()
            if self.resolution_note is not None
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

        if (
            normalized_resolution_note is not None
            and self.target_status is not OnboardingTaskStatus.IN_PROGRESS
        ):
            raise ValueError(
                "resolution_note is allowed only when target_status is in progress."
            )

        self.blocked_reason = normalized_reason
        self.resolution_note = normalized_resolution_note
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


class OnboardingTemplateTaskResponse(BaseModel):
    """One ordered task definition available for a new onboarding instance."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    title: str
    description: str | None
    due_offset_days: int | None
    default_assignee_role: Role | None
    responsible_party: OnboardingTaskResponsibility
    requires_document_upload: bool


class OnboardingTemplateListItemResponse(OnboardingTemplateResponse):
    """Active template metadata and its immutable task definitions."""

    tasks: list[OnboardingTemplateTaskResponse]


class OnboardingTemplateListResponse(BaseModel):
    """Available tenant onboarding templates."""

    items: list[OnboardingTemplateListItemResponse]


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


class OnboardingTaskDocumentResponse(BaseModel):
    """Safe metadata for an onboarding attachment, without storage credentials."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    onboarding_task_id: UUID
    original_filename: str
    declared_content_type: str
    expected_byte_size: int
    status: OnboardingTaskDocumentStatus
    uploaded_at: datetime | None
    scan_started_at: datetime | None
    scan_completed_at: datetime | None
    created_at: datetime


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
    responsible_party: OnboardingTaskResponsibility
    requires_document_upload: bool
    status: OnboardingTaskStatus
    completed_at: datetime | None
    blocked_reason: str | None
    resolution_note: str | None
    version: int
    documents: list[OnboardingTaskDocumentResponse] = Field(default_factory=list)


class OnboardingTaskDocumentCreateRequest(BaseModel):
    """Immutable upload metadata supplied by the authenticated employee."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    original_filename: str = Field(min_length=1, max_length=255)
    declared_content_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    expected_byte_size: int = Field(ge=1, le=10 * 1024 * 1024)
    checksum_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-fA-F0-9]{64}$",
    )

    @model_validator(mode="after")
    def validate_upload_metadata(self) -> "OnboardingTaskDocumentCreateRequest":
        """Keep path and control characters out of stored filenames."""
        if "/" in self.original_filename or "\\" in self.original_filename:
            raise ValueError("Document filename must not contain a path.")
        if any(ord(character) < 32 for character in self.original_filename):
            raise ValueError("Document filename contains invalid characters.")
        self.checksum_sha256 = self.checksum_sha256.lower()
        return self


class OnboardingTaskDocumentUploadAuthorizationRequest(BaseModel):
    """Empty body; all upload parameters come from the persisted intent."""

    model_config = ConfigDict(extra="forbid")


class OnboardingTaskDocumentConfirmUploadRequest(BaseModel):
    """Empty body; object storage verifies uploaded metadata server-side."""

    model_config = ConfigDict(extra="forbid")


class OnboardingTaskDocumentUploadAuthorizationResponse(BaseModel):
    """Short-lived URL for direct upload to private object storage."""

    upload_url: str = Field(min_length=1)
    required_headers: dict[str, str]
    expires_at: datetime


class OnboardingTaskDocumentDownloadAuthorizationResponse(BaseModel):
    """Short-lived URL for a scanned onboarding attachment."""

    url: str = Field(min_length=1)
    expires_at: datetime


class OnboardingTaskWorklistAssigneeResponse(BaseModel):
    """A current assignee that can be used to filter the worklist."""

    id: UUID
    display_name: str


class OnboardingTaskWorklistItemResponse(BaseModel):
    """A task row joined to safe new-hire and assignment context."""

    task: OnboardingTaskResponse
    application_id: UUID
    instance_status: OnboardingInstanceStatus
    employee_name: str
    job_title: str
    assignee_display_name: str | None
    step_number: int
    can_update: bool


class OnboardingTaskWorklistResponse(BaseModel):
    """Paginated workspace task worklist and available assignee filters."""

    items: list[OnboardingTaskWorklistItemResponse]
    assignees: list[OnboardingTaskWorklistAssigneeResponse]
    total: int
    page: int
    limit: int
    view: OnboardingTaskWorklistView


class OnboardingTaskActivityItemResponse(BaseModel):
    """One safe event in a task's onboarding timeline."""

    id: UUID
    event_type: OnboardingTaskEventType
    from_status: OnboardingTaskStatus | None
    to_status: OnboardingTaskStatus
    note: str | None
    actor_display_name: str
    occurred_at: datetime


class OnboardingTaskActivityResponse(BaseModel):
    """Chronological activity for one onboarding task."""

    items: list[OnboardingTaskActivityItemResponse]


class ApplicationOnboardingResponse(BaseModel):
    """An application's onboarding instance, when one has been started."""

    instance: OnboardingInstanceResponse | None
    tasks: list[OnboardingTaskResponse]


class EmployeePortalTaskResponse(BaseModel):
    """Employee-safe task details for the employee's own onboarding plan."""

    id: UUID
    title: str
    description: str | None
    due_at: datetime | None
    responsible_party: OnboardingTaskResponsibility
    requires_document_upload: bool
    status: OnboardingTaskStatus
    blocked_reason: str | None
    resolution_note: str | None
    completed_at: datetime | None
    version: int
    can_update: bool
    documents: list[OnboardingTaskDocumentResponse] = Field(default_factory=list)


class UpdateEmployeePortalTaskStatusRequest(BaseModel):
    """Allow an employee to progress or request help on their own task."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    target_status: Literal[
        OnboardingTaskStatus.IN_PROGRESS,
        OnboardingTaskStatus.COMPLETED,
        OnboardingTaskStatus.BLOCKED,
    ]
    blocked_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_blocked_reason(self) -> "UpdateEmployeePortalTaskStatusRequest":
        """Require a concise explanation when the employee requests help."""
        normalized_reason = (
            self.blocked_reason.strip()
            if self.blocked_reason is not None
            else None
        )

        if self.target_status is OnboardingTaskStatus.BLOCKED:
            if not normalized_reason:
                raise ValueError(
                    "blocked_reason is required when requesting help."
                )
        elif normalized_reason is not None:
            raise ValueError(
                "blocked_reason is allowed only when requesting help."
            )

        self.blocked_reason = normalized_reason
        return self


class EmployeePortalOnboardingResponse(BaseModel):
    """A signed-in employee's own profile summary and onboarding checklist."""

    profile: EmployeePortalProfileResponse
    onboarding_status: OnboardingInstanceStatus | None
    started_at: datetime | None
    completed_at: datetime | None
    tasks: list[EmployeePortalTaskResponse]


class OnboardingOverviewItemResponse(BaseModel):
    """One workspace onboarding plan with safe operational summary fields."""

    model_config = ConfigDict(extra="forbid")

    instance: OnboardingInstanceResponse
    employee_name: str
    job_title: str
    total_tasks: int
    completed_tasks: int
    overdue_tasks: int


class OnboardingOverviewResponse(BaseModel):
    """Workspace onboarding plans, ordered newest first."""

    items: list[OnboardingOverviewItemResponse]
    total: int
    page: int
    limit: int
    active_plan_count: int
    overdue_task_count: int
