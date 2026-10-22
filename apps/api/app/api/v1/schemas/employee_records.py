"""Private API contracts for MindHire employee records."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.employees.enums import (
    EmployeeOffboardingReason,
    EmployeeOffboardingTaskStatus,
    EmployeeStatus,
)


class CreateEmployeeRecordRequest(BaseModel):
    """Optional details to add when converting a hired application."""

    model_config = ConfigDict(extra="forbid")

    employee_number: str | None = Field(default=None, max_length=50)
    work_email: EmailStr | None = None
    start_date: date | None = None
    manager_user_id: UUID | None = None


class UpdateEmployeeRecordRequest(BaseModel):
    """Partial employee record update with optimistic concurrency."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    employee_number: str | None = Field(default=None, max_length=50)
    work_email: EmailStr | None = None
    start_date: date | None = None
    job_title: str | None = Field(default=None, min_length=1, max_length=200)
    department: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    manager_user_id: UUID | None = None
    status: EmployeeStatus | None = None


class LinkEmployeeAccountRequest(BaseModel):
    """Link an employee record to an existing workspace identity."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID | None
    expected_version: int = Field(ge=1)


class StartEmployeeOffboardingRequest(BaseModel):
    """Required details to start a planned employee departure."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    last_working_day: date
    reason: EmployeeOffboardingReason


class CancelEmployeeOffboardingRequest(BaseModel):
    """Concurrency precondition for cancelling planned offboarding."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class OffboardingTemplateTaskRequest(BaseModel):
    """One ordered task in the workspace offboarding template."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_days_before_last_working_day: int = Field(default=0, ge=0, le=365)


class ReplaceOffboardingTemplateRequest(BaseModel):
    """Complete replacement for the workspace's future offboarding checklist."""

    model_config = ConfigDict(extra="forbid")

    items: list[OffboardingTemplateTaskRequest] = Field(min_length=1, max_length=50)


class OffboardingTemplateTaskResponse(BaseModel):
    """Task definition shown in offboarding settings."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    title: str
    description: str | None
    due_days_before_last_working_day: int


class OffboardingTemplateResponse(BaseModel):
    """Workspace offboarding template and ordered task definitions."""

    items: list[OffboardingTemplateTaskResponse]


class EmployeeOffboardingTaskUpdateRequest(BaseModel):
    """Editable fields for an active offboarding checklist task."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    assigned_to_user_id: UUID | None = None
    due_date: date | None = None
    status: EmployeeOffboardingTaskStatus | None = None
    completion_notes: str | None = Field(default=None, max_length=4000)


class EmployeeOffboardingTaskResponse(BaseModel):
    """A task snapshot with current owner and completion information."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    title: str
    description: str | None
    due_date: date
    assigned_to_user_id: UUID | None
    assigned_to_name: str | None = None
    status: EmployeeOffboardingTaskStatus
    completion_notes: str | None
    completed_at: datetime | None
    version: int


class EmployeeOffboardingChecklistResponse(BaseModel):
    """Current cycle checklist with progress counts."""

    items: list[EmployeeOffboardingTaskResponse]
    completed_count: int
    total_count: int


class EmployeeOffboardingOverviewItemResponse(BaseModel):
    """One active offboarding case and its current checklist summary."""

    employee_id: UUID
    application_id: UUID
    employee_name: str
    job_title: str
    department: str | None
    location: str | None
    last_working_day: date | None
    reason: EmployeeOffboardingReason | None
    completed_task_count: int
    total_task_count: int
    overdue_task_count: int
    next_due_date: date | None


class EmployeeOffboardingOverviewResponse(BaseModel):
    """A paginated, filterable list of current offboarding cases."""

    model_config = ConfigDict(extra="forbid")

    items: list[EmployeeOffboardingOverviewItemResponse]
    total: int
    page: int
    limit: int


class LinkEmployeeAccountResponse(BaseModel):
    """Safe result of linking or unlinking an employee account."""

    employee_id: UUID
    user_id: UUID | None
    version: int


class EmployeeRecordResponse(BaseModel):
    """Internal employment details linked to a hired application."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    candidate_id: UUID
    employee_number: str | None
    work_email: str | None
    start_date: date | None
    job_title: str
    department: str | None
    location: str | None
    manager_user_id: UUID | None
    user_id: UUID | None
    status: EmployeeStatus
    last_working_day: date | None
    offboarding_reason: EmployeeOffboardingReason | None
    version: int
    created_at: datetime
    updated_at: datetime


class EmployeeDirectoryItemResponse(EmployeeRecordResponse):
    """Employee record fields needed to identify an employee in the directory."""

    employee_name: str


class EmployeeDirectoryResponse(BaseModel):
    """A page of tenant-scoped employee records."""

    model_config = ConfigDict(extra="forbid")

    items: list[EmployeeDirectoryItemResponse]
    total: int
    page: int
    limit: int


class EmployeeDirectoryFilterOptionsResponse(BaseModel):
    """Distinct employee values used to populate directory filters."""

    model_config = ConfigDict(extra="forbid")

    departments: list[str]
    locations: list[str]


class EmployeePortalProfileResponse(BaseModel):
    """Employee information visible to its linked account holder."""

    full_name: str
    work_email: str | None
    start_date: date | None
    job_title: str
    department: str | None
    location: str | None
    status: EmployeeStatus
