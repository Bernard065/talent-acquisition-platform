"""Private tenant-admin endpoints for HRIS connection management."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db_session,
    get_hris_credential_vault,
    get_tenant_context,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.hris_connections import (
    CreateHrisConnectionRequest,
    ExpectedHrisConnectionVersionRequest,
    HrisConnectionDeletedResponse,
    HrisConnectionListResponse,
    HrisConnectionResponse,
)
from app.core.authorization import Role, TenantContext
from app.services.hris_connection_lifecycle import (
    delete_hris_connection,
    disable_hris_connection,
    get_hris_connection,
    list_hris_connections,
)
from app.services.hris_connections import (
    CreateHrisConnectionCommand,
    create_hris_connection,
)
from app.services.hris_credentials import HrisCredentials, HrisCredentialVault
from app.services.hris_errors import HrisAccessDeniedError
from app.services.idempotency import IdempotencyResult, execute_idempotently

router = APIRouter(
    prefix="/hris-connections",
    tags=["HRIS connections"],
)


async def _require_hris_tenant_admin(
    context: Annotated[TenantContext, Depends(get_tenant_context)],
) -> TenantContext:
    """Require tenant-admin access before exposing HRIS configuration."""
    if Role.TENANT_ADMIN not in context.roles:
        raise HrisAccessDeniedError(
            "Tenant administrator permission is required for HRIS configuration."
        )

    return context


TenantAdminContext = Annotated[
    TenantContext,
    Depends(_require_hris_tenant_admin),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
HrisVault = Annotated[
    HrisCredentialVault,
    Depends(get_hris_credential_vault),
]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return idempotent private write data without intermediary caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _idempotency_payload(
    payload: CreateHrisConnectionRequest,
) -> dict[str, Any]:
    """
    Build a one-way idempotency fingerprint input.

    Credential values exist briefly in memory so changed credentials cannot
    replay a prior request. `execute_idempotently` persists only the SHA-256
    request fingerprint, never this payload.
    """
    return {
        "name": payload.name,
        "provider": payload.provider.value,
        "credentials": {
            name: value.get_secret_value()
            for name, value in payload.credentials.items()
        },
    }


@router.post(
    "",
    response_model=HrisConnectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an HRIS connection",
)
async def create_hris_connection_endpoint(
    payload: CreateHrisConnectionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    credential_vault: HrisVault,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one HRIS connection while storing credentials only in Infisical."""

    async def operation() -> tuple[int, dict[str, Any]]:
        connection = await create_hris_connection(
            session,
            context=context,
            command=CreateHrisConnectionCommand(
                name=payload.name,
                provider=payload.provider,
                credentials=HrisCredentials(values=payload.credentials),
            ),
            credential_vault=credential_vault,
        )

        response = HrisConnectionResponse.model_validate(connection)

        return (
            status.HTTP_201_CREATED,
            response.model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="hris_connection.create",
        payload=_idempotency_payload(payload),
        operation=operation,
    )

    return _private_response(result)


@router.get(
    "",
    response_model=HrisConnectionListResponse,
    summary="List HRIS connections",
)
async def list_hris_connections_endpoint(
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
) -> HrisConnectionListResponse:
    """List safe HRIS connection metadata for the caller tenant."""
    connections = await list_hris_connections(
        session,
        context=context,
    )

    response.headers["Cache-Control"] = "private, no-store"

    return HrisConnectionListResponse(
        items=[
            HrisConnectionResponse.model_validate(connection)
            for connection in connections
        ]
    )


@router.get(
    "/{connection_id}",
    response_model=HrisConnectionResponse,
    summary="Get an HRIS connection",
)
async def get_hris_connection_endpoint(
    connection_id: UUID,
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
) -> HrisConnectionResponse:
    """Return safe metadata for one tenant-owned HRIS connection."""
    connection = await get_hris_connection(
        session,
        context=context,
        connection_id=connection_id,
    )

    response.headers["Cache-Control"] = "private, no-store"

    return HrisConnectionResponse.model_validate(connection)


@router.post(
    "/{connection_id}/disable",
    response_model=HrisConnectionResponse,
    summary="Disable an HRIS connection",
)
async def disable_hris_connection_endpoint(
    connection_id: UUID,
    payload: ExpectedHrisConnectionVersionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Disable future onboarding handoffs using optimistic concurrency."""

    async def operation() -> tuple[int, dict[str, Any]]:
        connection = await disable_hris_connection(
            session,
            context=context,
            connection_id=connection_id,
            expected_version=payload.expected_version,
        )
        response = HrisConnectionResponse.model_validate(connection)

        return status.HTTP_200_OK, response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"hris_connection.disable:{connection_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )

    return _private_response(result)


@router.delete(
    "/{connection_id}",
    response_model=HrisConnectionDeletedResponse,
    summary="Logically delete a disabled HRIS connection",
)
async def delete_hris_connection_endpoint(
    connection_id: UUID,
    payload: ExpectedHrisConnectionVersionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Logically delete a disabled connection while preserving retention data."""

    async def operation() -> tuple[int, dict[str, Any]]:
        await delete_hris_connection(
            session,
            context=context,
            connection_id=connection_id,
            expected_version=payload.expected_version,
        )

        return (
            status.HTTP_200_OK,
            HrisConnectionDeletedResponse(
                id=connection_id,
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"hris_connection.delete:{connection_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )

    return _private_response(result)
