"""Private tenant-admin API for outbound webhook endpoint management."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import require_any_role
from app.api.dependencies import (
    get_db_session,
    get_webhook_signing_secret_vault,
)
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.webhooks import (
    CreateWebhookEndpointRequest,
    ExpectedWebhookEndpointVersionRequest,
    UpdateWebhookEndpointRequest,
    WebhookEndpointDeletedResponse,
    WebhookEndpointListResponse,
    WebhookEndpointResponse,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.webhook import WebhookEndpoint, WebhookSubscription
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.webhook_management import (
    CreateWebhookEndpointCommand,
    UpdateWebhookEndpointCommand,
    create_webhook_endpoint,
    delete_webhook_endpoint,
    disable_webhook_endpoint,
    rotate_webhook_endpoint_secret,
    update_webhook_endpoint,
)
from app.services.webhook_management_errors import WebhookEndpointNotFoundError
from app.services.webhook_secrets import WebhookSigningSecretVault

router = APIRouter(
    prefix="/webhook-endpoints",
    tags=["Webhook endpoints"],
)

TenantAdminContext = Annotated[
    TenantContext,
    Depends(require_any_role(Role.TENANT_ADMIN)),
]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
SigningSecretVault = Annotated[
    WebhookSigningSecretVault,
    Depends(get_webhook_signing_secret_vault),
]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return idempotent private data without intermediary caching."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _allowed_hosts(request: Request) -> list[str]:
    """Read only operator-configured outbound destination allow-list entries."""
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are unavailable.")

    return settings.webhook_allowed_hosts


async def _endpoint_response(
    session: AsyncSession,
    *,
    endpoint: WebhookEndpoint,
) -> WebhookEndpointResponse:
    """Serialize safe endpoint metadata and tenant-owned subscriptions."""

    event_types = list(
        await session.scalars(
            select(WebhookSubscription.event_type)
            .where(
                WebhookSubscription.tenant_id == endpoint.tenant_id,
                WebhookSubscription.webhook_endpoint_id == endpoint.id,
            )
            .order_by(WebhookSubscription.event_type)
        )
    )

    return WebhookEndpointResponse(
        id=endpoint.id,
        name=endpoint.name,
        url=endpoint.url,
        status=endpoint.status,
        event_types=event_types,
        version=endpoint.version,
        created_at=endpoint.created_at,
        updated_at=endpoint.updated_at,
    )


async def _load_endpoint(
    session: AsyncSession,
    *,
    context: TenantContext,
    webhook_endpoint_id: UUID,
) -> WebhookEndpoint:
    """Load one endpoint only from the authenticated caller's tenant."""

    endpoint = await session.scalar(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == webhook_endpoint_id,
            WebhookEndpoint.tenant_id == context.tenant_id,
        )
    )

    if endpoint is None:
        raise WebhookEndpointNotFoundError("Webhook endpoint was not found.")

    return endpoint


@router.post(
    "",
    response_model=WebhookEndpointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an outbound webhook endpoint",
)
async def create_webhook_endpoint_endpoint(
    payload: CreateWebhookEndpointRequest,
    request: Request,
    context: TenantAdminContext,
    session: DatabaseSession,
    signing_secret_vault: SigningSecretVault,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create one allow-listed HTTPS endpoint and its subscriptions."""

    async def operation() -> tuple[int, dict[str, Any]]:
        endpoint = await create_webhook_endpoint(
            session,
            context=context,
            command=CreateWebhookEndpointCommand(
                name=payload.name,
                url=payload.url,
                event_types=tuple(payload.event_types),
            ),
            signing_secret_vault=signing_secret_vault,
            allowed_hosts=_allowed_hosts(request),
        )
        response = await _endpoint_response(session, endpoint=endpoint)

        return status.HTTP_201_CREATED, response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name="webhook_endpoint.create",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.get(
    "",
    response_model=WebhookEndpointListResponse,
    summary="List tenant webhook endpoints",
)
async def list_webhook_endpoints_endpoint(
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
) -> WebhookEndpointListResponse:
    """Return safe endpoint configuration for the caller's tenant."""

    endpoints = list(
        await session.scalars(
            select(WebhookEndpoint)
            .where(WebhookEndpoint.tenant_id == context.tenant_id)
            .order_by(WebhookEndpoint.created_at.desc(), WebhookEndpoint.id.desc())
            .limit(100)
        )
    )

    response.headers["Cache-Control"] = "private, no-store"

    return WebhookEndpointListResponse(
        items=[
            await _endpoint_response(session, endpoint=endpoint)
            for endpoint in endpoints
        ]
    )


@router.get(
    "/{webhook_endpoint_id}",
    response_model=WebhookEndpointResponse,
    summary="Get a webhook endpoint",
)
async def get_webhook_endpoint_endpoint(
    webhook_endpoint_id: UUID,
    context: TenantAdminContext,
    session: DatabaseSession,
    response: Response,
) -> WebhookEndpointResponse:
    """Return one safe tenant-owned endpoint configuration."""

    endpoint = await _load_endpoint(
        session,
        context=context,
        webhook_endpoint_id=webhook_endpoint_id,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return await _endpoint_response(session, endpoint=endpoint)


@router.put(
    "/{webhook_endpoint_id}",
    response_model=WebhookEndpointResponse,
    summary="Replace webhook endpoint configuration",
)
async def update_webhook_endpoint_endpoint(
    webhook_endpoint_id: UUID,
    payload: UpdateWebhookEndpointRequest,
    request: Request,
    context: TenantAdminContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Replace metadata and the complete subscription set."""

    async def operation() -> tuple[int, dict[str, Any]]:
        endpoint = await update_webhook_endpoint(
            session,
            context=context,
            webhook_endpoint_id=webhook_endpoint_id,
            expected_version=payload.expected_version,
            command=UpdateWebhookEndpointCommand(
                name=payload.name,
                url=payload.url,
                event_types=tuple(payload.event_types),
            ),
            allowed_hosts=_allowed_hosts(request),
        )
        endpoint_response = await _endpoint_response(session, endpoint=endpoint)

        return status.HTTP_200_OK, endpoint_response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"webhook_endpoint.update:{webhook_endpoint_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/{webhook_endpoint_id}/secret-rotations",
    response_model=WebhookEndpointResponse,
    summary="Rotate webhook signing secret",
)
async def rotate_webhook_endpoint_secret_endpoint(
    webhook_endpoint_id: UUID,
    payload: ExpectedWebhookEndpointVersionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    signing_secret_vault: SigningSecretVault,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Rotate the external signing secret without returning secret material."""

    async def operation() -> tuple[int, dict[str, Any]]:
        endpoint = await rotate_webhook_endpoint_secret(
            session,
            context=context,
            webhook_endpoint_id=webhook_endpoint_id,
            expected_version=payload.expected_version,
            signing_secret_vault=signing_secret_vault,
        )
        endpoint_response = await _endpoint_response(session, endpoint=endpoint)

        return status.HTTP_200_OK, endpoint_response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"webhook_endpoint.rotate_secret:{webhook_endpoint_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.post(
    "/{webhook_endpoint_id}/disable",
    response_model=WebhookEndpointResponse,
    summary="Disable a webhook endpoint",
)
async def disable_webhook_endpoint_endpoint(
    webhook_endpoint_id: UUID,
    payload: ExpectedWebhookEndpointVersionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Disable future endpoint fan-out using optimistic concurrency."""

    async def operation() -> tuple[int, dict[str, Any]]:
        endpoint = await disable_webhook_endpoint(
            session,
            context=context,
            webhook_endpoint_id=webhook_endpoint_id,
            expected_version=payload.expected_version,
        )
        endpoint_response = await _endpoint_response(session, endpoint=endpoint)

        return status.HTTP_200_OK, endpoint_response.model_dump(mode="json")

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"webhook_endpoint.disable:{webhook_endpoint_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)


@router.delete(
    "/{webhook_endpoint_id}",
    response_model=WebhookEndpointDeletedResponse,
    summary="Logically delete a webhook endpoint",
)
async def delete_webhook_endpoint_endpoint(
    webhook_endpoint_id: UUID,
    payload: ExpectedWebhookEndpointVersionRequest,
    context: TenantAdminContext,
    session: DatabaseSession,
    signing_secret_vault: SigningSecretVault,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Disable the endpoint, unsubscribe it, and revoke its vault secret."""

    async def operation() -> tuple[int, dict[str, Any]]:
        await delete_webhook_endpoint(
            session,
            context=context,
            webhook_endpoint_id=webhook_endpoint_id,
            expected_version=payload.expected_version,
            signing_secret_vault=signing_secret_vault,
        )

        return (
            status.HTTP_200_OK,
            WebhookEndpointDeletedResponse(
                id=webhook_endpoint_id
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=f"webhook_endpoint.delete:{webhook_endpoint_id}",
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
