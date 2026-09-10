"""Version 1 private self-service notification preference endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.idempotency import IdempotencyKey, idempotency_response
from app.api.v1.schemas.notifications import (
    NotificationPreferenceResponse,
    UpdateNotificationPreferenceRequest,
)
from app.core.authorization import TenantContext
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationEventType,
)
from app.services.idempotency import IdempotencyResult, execute_idempotently
from app.services.notification_preferences import (
    list_notification_preferences,
    update_notification_preference,
)

router = APIRouter(tags=["Notification preferences"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _private_response(result: IdempotencyResult) -> JSONResponse:
    """Return replay-safe preference responses without caching user settings."""
    response = idempotency_response(result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@router.get(
    "/notification-preferences",
    response_model=list[NotificationPreferenceResponse],
    summary="List my notification preferences",
)
async def list_notification_preferences_endpoint(
    response: Response,
    context: CallerContext,
    session: DatabaseSession,
) -> list[NotificationPreferenceResponse]:
    """Return all effective preferences for the authenticated user."""
    response.headers["Cache-Control"] = "private, no-store"

    preferences = await list_notification_preferences(
        session,
        context=context,
    )
    return [
        NotificationPreferenceResponse.model_validate(preference)
        for preference in preferences
    ]


@router.put(
    "/notification-preferences/{event_type}/{channel}",
    response_model=NotificationPreferenceResponse,
    summary="Update my notification preference",
)
async def update_notification_preference_endpoint(
    event_type: NotificationEventType,
    channel: NotificationChannel,
    payload: UpdateNotificationPreferenceRequest,
    context: CallerContext,
    session: DatabaseSession,
    idempotency_key: IdempotencyKey,
) -> JSONResponse:
    """Create or update only the verified caller's tenant-local preference."""

    async def operation() -> tuple[int, dict[str, Any]]:
        preference = await update_notification_preference(
            session,
            context=context,
            event_type=event_type,
            channel=channel,
            enabled=payload.enabled,
            expected_version=payload.expected_version,
        )
        return (
            status.HTTP_200_OK,
            NotificationPreferenceResponse.model_validate(
                preference
            ).model_dump(mode="json"),
        )

    result = await execute_idempotently(
        session,
        context=context,
        key=idempotency_key,
        operation_name=(
            "notification_preference.update:"
            f"{event_type.value}:{channel.value}"
        ),
        payload=payload.model_dump(mode="json"),
        operation=operation,
    )
    return _private_response(result)
