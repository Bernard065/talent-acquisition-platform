"""Version 1 requisition approval HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.approvals import (
    ApprovalApproverResponse,
    ApprovalDecisionRequest,
    ApprovalPolicyApproversUpdateRequest,
    ApprovalPolicyConfigurationResponse,
    ApprovalPolicyCreateRequest,
    ApprovalPolicyResponse,
    RequisitionApprovalInboxResponse,
    RequisitionApprovalReviewResponse,
    RequisitionApprovalResponse,
)
from app.core.authorization import TenantContext
from app.db.models.approval import RequisitionApproval, RequisitionApprovalDecision
from app.db.models.requisition import Requisition
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.services.idempotency import execute_idempotently
from app.services.requisition_approvals import (
    CreateApprovalPolicyCommand,
    approve_requisition_approval,
    create_approval_policy,
    get_approval_policy_configuration,
    get_assigned_requisition_approval,
    list_assigned_requisition_approvals,
    reject_requisition_approval,
    set_default_approval_policy,
    submit_requisition_for_approval,
    update_approval_policy_approvers,
)

router = APIRouter(tags=["Requisition approvals"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _review_response(
    approval: RequisitionApproval,
    requisition: Requisition,
    decision: RequisitionApprovalDecision,
) -> RequisitionApprovalReviewResponse:
    return RequisitionApprovalReviewResponse(
        approval_id=approval.id,
        requisition_id=requisition.id,
        title=requisition.title,
        description=requisition.description,
        department=requisition.department,
        location=requisition.location,
        headcount=requisition.headcount,
        requisition_status=requisition.status,
        approval_status=approval.status,
        current_step=approval.current_step,
        assigned_step=decision.step_position,
        assigned_decision_status=decision.status,
        is_current_approver=(
            approval.status is ApprovalStatus.PENDING
            and decision.status is ApprovalDecisionStatus.PENDING
            and decision.step_position == approval.current_step
        ),
        submitted_by_subject=approval.submitted_by_subject,
        submitted_at=approval.submitted_at,
        completed_at=approval.completed_at,
    )


@router.get(
    "/requisition-approvals/inbox",
    response_model=RequisitionApprovalInboxResponse,
    summary="List requisitions assigned to the current approver",
)
async def list_assigned_requisition_approvals_endpoint(
    context: CallerContext,
    session: DatabaseSession,
) -> RequisitionApprovalInboxResponse:
    """List pending requisitions on the authenticated user's approval chain."""
    rows = await list_assigned_requisition_approvals(session, context=context)
    return RequisitionApprovalInboxResponse(
        items=[
            _review_response(approval, requisition, decision)
            for approval, requisition, decision in rows
        ]
    )


@router.get(
    "/requisition-approvals/{approval_id}",
    response_model=RequisitionApprovalReviewResponse,
    summary="Get an assigned requisition approval",
)
async def get_assigned_requisition_approval_endpoint(
    approval_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
) -> RequisitionApprovalReviewResponse:
    """Return requisition details only to an assigned approval-chain member."""
    approval, requisition, decision = await get_assigned_requisition_approval(
        session,
        context=context,
        approval_id=approval_id,
    )
    return _review_response(approval, requisition, decision)


@router.patch(
    "/approval-policies/{policy_id}/approvers",
    response_model=ApprovalPolicyResponse,
    summary="Update default approval policy approvers",
)
async def update_approval_policy_approvers_endpoint(
    policy_id: UUID,
    payload: ApprovalPolicyApproversUpdateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Replace ordered approvers used by future requisition submissions."""

    async def operation() -> tuple[int, dict[str, Any]]:
        policy = await update_approval_policy_approvers(
            session,
            context=context,
            policy_id=policy_id,
            approver_user_ids=tuple(payload.approver_user_ids),
        )
        return (
            status.HTTP_200_OK,
            ApprovalPolicyResponse.model_validate(policy).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"approval_policy.update_approvers:{policy_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)


@router.get(
    "/approval-policies/configuration",
    response_model=ApprovalPolicyConfigurationResponse,
    summary="Get approval policy configuration",
)
async def get_approval_policy_configuration_endpoint(
    context: CallerContext,
    session: DatabaseSession,
) -> ApprovalPolicyConfigurationResponse:
    """Return the default policy and tenant members available as approvers."""
    policy, members, approver_user_ids = await get_approval_policy_configuration(
        session,
        context=context,
    )
    return ApprovalPolicyConfigurationResponse(
        default_policy=(
            ApprovalPolicyResponse.model_validate(policy)
            if policy is not None
            else None
        ),
        default_approver_user_ids=approver_user_ids,
        available_approvers=[
            ApprovalApproverResponse(
                id=member.id,
                display_name=member.display_name,
                email=member.email,
                is_current_user=member.external_subject == context.subject,
            )
            for member in members
        ],
    )


@router.post(
    "/approval-policies",
    response_model=ApprovalPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an approval policy",
)
async def create_approval_policy_endpoint(
    payload: ApprovalPolicyCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create a tenant approval policy with ordered named approvers."""

    async def operation() -> tuple[int, dict[str, Any]]:
        policy = await create_approval_policy(
            session,
            context=context,
            command=CreateApprovalPolicyCommand(
                name=payload.name,
                approver_user_ids=tuple(payload.approver_user_ids),
                is_default=payload.is_default,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            ApprovalPolicyResponse.model_validate(policy).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="approval_policy.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)


@router.post(
    "/approval-policies/{policy_id}/default",
    response_model=ApprovalPolicyResponse,
    summary="Set the tenant default approval policy",
)
async def set_default_approval_policy_endpoint(
    policy_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Set one active tenant policy as the default for future submissions."""

    async def operation() -> tuple[int, dict[str, Any]]:
        policy = await set_default_approval_policy(
            session,
            context=context,
            policy_id=policy_id,
        )
        return (
            status.HTTP_200_OK,
            ApprovalPolicyResponse.model_validate(policy).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"approval_policy.set_default:{policy_id}",
        payload={},
        operation=operation,
    )
    return idempotency_response(result)


@router.post(
    "/requisitions/{requisition_id}/approval-submissions",
    response_model=RequisitionApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a requisition for approval",
)
async def submit_requisition_for_approval_endpoint(
    requisition_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Snapshot the active default policy and submit a draft requisition."""

    async def operation() -> tuple[int, dict[str, Any]]:
        approval = await submit_requisition_for_approval(
            session,
            context=context,
            requisition_id=requisition_id,
        )
        return (
            status.HTTP_201_CREATED,
            RequisitionApprovalResponse.model_validate(approval).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"requisition.submit_for_approval:{requisition_id}",
        payload={},
        operation=operation,
    )
    return idempotency_response(result)


@router.post(
    "/requisition-approvals/{approval_id}/approve",
    response_model=RequisitionApprovalResponse,
    summary="Approve the current approval step",
)
async def approve_requisition_approval_endpoint(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Approve the step assigned to the verified tenant user."""

    async def operation() -> tuple[int, dict[str, Any]]:
        approval = await approve_requisition_approval(
            session,
            context=context,
            approval_id=approval_id,
            comment=payload.comment,
        )
        return (
            status.HTTP_200_OK,
            RequisitionApprovalResponse.model_validate(approval).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"requisition_approval.approve:{approval_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)


@router.post(
    "/requisition-approvals/{approval_id}/reject",
    response_model=RequisitionApprovalResponse,
    summary="Reject the current approval step",
)
async def reject_requisition_approval_endpoint(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Reject the step assigned to the verified tenant user."""

    async def operation() -> tuple[int, dict[str, Any]]:
        approval = await reject_requisition_approval(
            session,
            context=context,
            approval_id=approval_id,
            comment=payload.comment,
        )
        return (
            status.HTTP_200_OK,
            RequisitionApprovalResponse.model_validate(approval).model_dump(
                mode="json"
            ),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"requisition_approval.reject:{approval_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)
