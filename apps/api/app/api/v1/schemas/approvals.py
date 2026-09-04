"""Request and response schemas for requisition approval endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.approvals.enums import ApprovalStatus


class ApprovalPolicyCreateRequest(BaseModel):
    """Input for a sequential named-approver policy."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    approver_user_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]
    is_default: bool = False


class ApprovalPolicyResponse(BaseModel):
    """Public representation of an approval policy."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int
    is_default: bool
    is_active: bool
    created_at: datetime


class ApprovalDecisionRequest(BaseModel):
    """Optional comment accompanying an approval decision."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    comment: str | None = Field(default=None, max_length=5_000)


class RequisitionApprovalResponse(BaseModel):
    """Public representation of one requisition approval instance."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_id: UUID
    approval_policy_id: UUID
    status: ApprovalStatus
    current_step: int
    submitted_by_subject: str
    submitted_at: datetime
    completed_at: datetime | None
