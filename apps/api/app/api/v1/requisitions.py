"""Requisition HTTP endpoints."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db_session,
    get_tenant_context,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.requisitions import (
    RequisitionCreateRequest,
    RequisitionListResponse,
    RequisitionResponse,
    RequisitionTransitionRequest,
    RequisitionUpdateRequest,
)
from app.core.authorization import TenantContext
from app.services.idempotency import execute_idempotently
from app.services.requisition_workflow import transition_requisition_status
from app.services.requisitions import (
    CreateRequisitionCommand,
    UpdateRequisitionCommand,
    create_requisition,
    get_requisition,
    list_requisitions,
    update_requisition,
)

router = APIRouter(prefix="/requisitions", tags=["Requisitions"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.post(
    "",
    response_model=RequisitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a requisition",
)
async def create_requisition_endpoint(
    payload: RequisitionCreateRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create a draft requisition once for the supplied idempotency key."""

    async def operation() -> tuple[int, dict[str, Any]]:
        requisition = await create_requisition(
            session,
            context=context,
            command=CreateRequisitionCommand(
                title=payload.title,
                description=payload.description,
                department=payload.department,
                location=payload.location,
                headcount=payload.headcount,
            ),
        )
        return (
            status.HTTP_201_CREATED,
            RequisitionResponse.model_validate(requisition).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="requisition.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)


@router.get(
    "",
    response_model=RequisitionListResponse,
    summary="List requisitions",
)
async def list_requisitions_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
) -> RequisitionListResponse:
    """List tenant-owned requisitions using opaque keyset pagination."""
    page = await list_requisitions(
        session,
        context=context,
        limit=limit,
        cursor=cursor,
    )
    return RequisitionListResponse(
        items=[
            RequisitionResponse.model_validate(requisition)
            for requisition in page.items
        ],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{requisition_id}",
    response_model=RequisitionResponse,
    summary="Get a requisition",
)
async def get_requisition_endpoint(
    requisition_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
) -> RequisitionResponse:
    """Return one requisition visible to the verified caller's tenant."""
    requisition = await get_requisition(
        session,
        context=context,
        requisition_id=requisition_id,
    )
    return RequisitionResponse.model_validate(requisition)


@router.patch(
    "/{requisition_id}",
    response_model=RequisitionResponse,
    summary="Update a draft requisition",
)
async def update_requisition_endpoint(
    requisition_id: UUID,
    payload: RequisitionUpdateRequest,
    context: CallerContext,
    session: DatabaseSession,
) -> RequisitionResponse:
    """Update permitted fields of a tenant-owned draft requisition."""
    requisition = await update_requisition(
        session,
        context=context,
        requisition_id=requisition_id,
        command=UpdateRequisitionCommand(
            changes=payload.model_dump(exclude_unset=True),
        ),
    )
    return RequisitionResponse.model_validate(requisition)


@router.post(
    "/{requisition_id}/transitions",
    response_model=RequisitionResponse,
    summary="Transition requisition workflow status",
)
async def transition_requisition_endpoint(
    requisition_id: UUID,
    payload: RequisitionTransitionRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Apply one workflow transition for the supplied idempotency key."""

    async def operation() -> tuple[int, dict[str, Any]]:
        requisition = await transition_requisition_status(
            session,
            context=context,
            requisition_id=requisition_id,
            target_status=payload.target_status,
        )
        return (
            status.HTTP_200_OK,
            RequisitionResponse.model_validate(requisition).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"requisition.transition:{requisition_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return idempotency_response(result)
