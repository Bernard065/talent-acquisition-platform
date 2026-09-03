"""Request and response schemas for requisition endpoints."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.requisitions.enums import RequisitionStatus


class RequisitionCreateRequest(BaseModel):
    """Validated input for creating a requisition."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    department: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    headcount: int = Field(default=1, ge=1, le=10_000)


class RequisitionUpdateRequest(BaseModel):
    """Validated mutable fields for a draft requisition.

    Status is deliberately excluded. Workflow changes use the dedicated
    transition endpoint and application service.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    department: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    headcount: int | None = Field(default=None, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        """Require at least one field and protect required model attributes."""
        if not self.model_fields_set:
            raise ValueError("At least one field must be supplied.")

        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null.")

        if "headcount" in self.model_fields_set and self.headcount is None:
            raise ValueError("headcount cannot be null.")

        return self


class RequisitionTransitionRequest(BaseModel):
    """Validated input for a requisition workflow transition."""

    model_config = ConfigDict(extra="forbid")

    target_status: RequisitionStatus


class RequisitionResponse(BaseModel):
    """Public representation of a requisition."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    department: str | None
    location: str | None
    headcount: int
    status: RequisitionStatus
    version: int
    created_by_subject: str
    created_at: datetime
    updated_at: datetime


class RequisitionListResponse(BaseModel):
    """Cursor-paginated requisition collection."""

    items: list[RequisitionResponse]
    next_cursor: str | None = None
