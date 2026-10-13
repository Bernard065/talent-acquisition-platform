"""Private dashboard action-item endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.notification_action_items import (
    NotificationActionItem,
    NotificationActionItemsResponse,
)
from app.core.authorization import TenantContext
from app.services.notification_action_items import list_notification_action_items

router = APIRouter(prefix="/notifications", tags=["Notifications"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/action-items",
    response_model=NotificationActionItemsResponse,
    summary="List actions needing the caller's attention",
)
async def notification_action_items_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> NotificationActionItemsResponse:
    items = await list_notification_action_items(session, context=context)
    response.headers["Cache-Control"] = "private, no-store"
    return NotificationActionItemsResponse(
        items=[NotificationActionItem.model_validate(item) for item in items]
    )
