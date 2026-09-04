"""Version 1 requisition approval HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.approvals import (
    ApprovalDecisionRequest,
    ApprovalPolicyCreateRequest,
    ApprovalPolicyResponse,
    RequisitionApprovalResponse,
)
from app.core.authorization import TenantContext
from app.services.idempotency import execute_idempotently
from app.services.requisition_approvals import (
    CreateApprovalPolicyCommand,
    approve_requisition_approval,
    create_approval_policy,
    reject_requisition_approval,
    set_default_approval_policy,
    submit_requisition_for_approval,
)

router = APIRouter(tags=["Requisition approvals"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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
