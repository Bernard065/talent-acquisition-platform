"""Private API contracts for MindHire employee records."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.domains.employees.enums import EmployeeStatus


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
    status: EmployeeStatus
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
