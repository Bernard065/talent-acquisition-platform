"""Request and response schemas for requisition approval endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.requisitions.enums import RequisitionStatus


class ApprovalPolicyCreateRequest(BaseModel):
    """Input for a sequential named-approver policy."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    approver_user_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]
    is_default: bool = False


class ApprovalPolicyApproversUpdateRequest(BaseModel):
    """Replacement ordered approver list for an existing policy."""

    model_config = ConfigDict(extra="forbid")

    approver_user_ids: Annotated[list[UUID], Field(min_length=1, max_length=20)]


class ApprovalPolicyResponse(BaseModel):
    """Public representation of an approval policy."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    version: int
    is_default: bool
    is_active: bool
    created_at: datetime


class ApprovalApproverResponse(BaseModel):
    """Workspace member who can be assigned to an approval policy."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    display_name: str
    email: str
    is_current_user: bool


class ApprovalPolicyConfigurationResponse(BaseModel):
    """Current default approval policy and members available to assign."""

    default_policy: ApprovalPolicyResponse | None
    default_approver_user_ids: list[UUID]
    available_approvers: list[ApprovalApproverResponse]


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


class RequisitionApprovalReviewResponse(BaseModel):
    """Requisition details visible to a user assigned to its approval chain."""

    approval_id: UUID
    requisition_id: UUID
    title: str
    description: str | None
    department: str | None
    location: str | None
    headcount: int
    requisition_status: RequisitionStatus
    approval_status: ApprovalStatus
    current_step: int
    assigned_step: int
    assigned_decision_status: ApprovalDecisionStatus
    is_current_approver: bool
    submitted_by_subject: str
    submitted_at: datetime
    completed_at: datetime | None


class RequisitionApprovalInboxResponse(BaseModel):
    """Pending approvals assigned to the authenticated tenant user."""

    items: list[RequisitionApprovalReviewResponse]
