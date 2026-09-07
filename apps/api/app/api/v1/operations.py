"""Version 1 tenant operational-inspection endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.outbox import (
    DeadLetterEventListResponse,
    DeadLetterEventResponse,
)
from app.core.authorization import TenantContext
from app.services.outbox_inspection import list_dead_letter_events

router = APIRouter(prefix="/operations/outbox", tags=["Operations"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/dead-letters",
    response_model=DeadLetterEventListResponse,
    summary="List tenant dead-letter events",
)
async def list_dead_letter_events_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=1_024)] = None,
) -> DeadLetterEventListResponse:
    """
    List failed asynchronous work for the caller's tenant.

    Authorization is enforced by the application service: only tenant
    administrators may inspect dead-letter records.
    """
    page = await list_dead_letter_events(
        session,
        context=context,
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"

    items: list[DeadLetterEventResponse] = []
    for event in page.items:
        if event.dead_lettered_at is None:
            raise RuntimeError("Dead-letter event is missing its timestamp.")

        items.append(
            DeadLetterEventResponse(
                id=event.id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                attempts=event.attempts,
                last_error=event.last_error,
                created_at=event.created_at,
                dead_lettered_at=event.dead_lettered_at,
            )
        )

    return DeadLetterEventListResponse(
        items=items,
        next_cursor=page.next_cursor,
    )
