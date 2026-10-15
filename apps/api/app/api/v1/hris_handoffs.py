"""Private tenant-admin endpoints for HRIS handoff operations."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.hris_handoffs import (
    HrisHandoffOperationListResponse,
    HrisHandoffOperationResponse,
    RetryHrisHandoffRequest,
)
from app.core.authorization import Role, TenantContext
from app.domains.hris.enums import HrisHandoffStatus
from app.services.hris_errors import HrisAccessDeniedError
from app.services.hris_handoff_operations import (
    HrisHandoffOperation,
    get_hris_handoff_operation,
    list_hris_handoff_operations,
    retry_failed_hris_handoff,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(
    prefix="/hris/handoffs",
    tags=["HRIS handoffs"],
)


async def _require_hris_tenant_admin(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    """Require tenant-admin access before exposing HRIS operational metadata."""
    if Role.TENANT_ADMIN not in context.roles:
        raise HrisAccessDeniedError(
            "Tenant administrator permission is required for HRIS operations."
        )

    return context


TenantAdminContext = Annotated[
    TenantContext,
    Depends(_require_hris_tenant_admin),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _to_response(
    operation: HrisHandoffOperation,
) -> HrisHandoffOperationResponse:
    """Convert a safe service result into its public API representation."""
    handoff = operation.handoff

    return HrisHandoffOperationResponse(
        id=handoff.id,
        provider=operation.provider,
        status=handoff.status,
        version=handoff.version,
        attempt_count=handoff.attempt_count,
        last_error_code=handoff.last_error_code,
        last_attempt_at=handoff.last_attempt_at,
        succeeded_at=handoff.succeeded_at,
        external_employee_reference=handoff.external_employee_reference,
        created_at=handoff.created_at,
        updated_at=handoff.updated_at,
    )


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return an idempotent handoff mutation without intermediary caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get(
    "",
    response_model=HrisHandoffOperationListResponse,
    summary="List HRIS handoff operations",
)
async def list_hris_handoff_operations_endpoint(
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=1_024)] = None,
    handoff_status: Annotated[
        HrisHandoffStatus | None,
        Query(alias="status"),
    ] = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> HrisHandoffOperationListResponse:
    """List safe tenant-local HRIS handoff execution state."""
    page = await list_hris_handoff_operations(
        session,
        context=context,
        status=handoff_status,
        created_from=created_from,
        created_to=created_to,
        cursor=cursor,
        limit=limit,
    )

    response.headers["Cache-Control"] = "private, no-store"

    return HrisHandoffOperationListResponse(
        items=[_to_response(operation) for operation in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{handoff_id}",
    response_model=HrisHandoffOperationResponse,
    summary="Get an HRIS handoff operation",
)
async def get_hris_handoff_operation_endpoint(
    handoff_id: UUID,
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
) -> HrisHandoffOperationResponse:
    """Return safe state for one tenant-owned HRIS handoff."""
    operation = await get_hris_handoff_operation(
        session,
        context=context,
        handoff_id=handoff_id,
    )

    response.headers["Cache-Control"] = "private, no-store"

    return _to_response(operation)


@router.post(
    "/{handoff_id}/retry",
    response_model=HrisHandoffOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Retry a terminally failed HRIS handoff",
)
async def retry_hris_handoff_endpoint(
    handoff_id: UUID,
    payload: RetryHrisHandoffRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Queue an audited retry for a failed tenant-owned handoff."""

    async def operation() -> tuple[int, dict[str, object]]:
        handoff_operation = await retry_failed_hris_handoff(
            session,
            context=context,
            handoff_id=handoff_id,
            expected_version=payload.expected_version,
        )
        response = _to_response(handoff_operation)
        return status.HTTP_200_OK, response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"hris_handoff.retry:{handoff_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
