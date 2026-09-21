"""Private tenant-admin endpoints for HRIS handoff operations."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.hris_handoffs import (
    HrisHandoffOperationListResponse,
    HrisHandoffOperationResponse,
)
from app.core.authorization import Role, TenantContext
from app.domains.hris.enums import HrisHandoffStatus
from app.services.hris_errors import HrisAccessDeniedError
from app.services.hris_handoff_operations import (
    HrisHandoffOperation,
    get_hris_handoff_operation,
    list_hris_handoff_operations,
)

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
