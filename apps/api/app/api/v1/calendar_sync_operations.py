"""Workspace-admin calendar synchronization monitoring endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.interviews import (
    CalendarSyncOperationItemResponse,
    CalendarSyncOperationsListResponse,
    InterviewCalendarSyncRetryResponse,
)
from app.core.authorization import TenantContext
from app.core.config import Settings
from app.domains.calendar.enums import InterviewCalendarSyncStatus
from app.services.calendar_sync_operations import (
    list_calendar_sync_operations,
    retry_calendar_sync_as_admin,
)
from app.services.interview_calendar_sync import (
    CalendarSyncRetryAlreadyQueuedError,
    CalendarSyncRetryUnavailableError,
)

router = APIRouter(prefix="/operations/calendar-syncs", tags=["Calendar operations"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "",
    response_model=CalendarSyncOperationsListResponse,
    summary="List workspace calendar deliveries",
)
async def list_calendar_sync_operations_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[
        InterviewCalendarSyncStatus | None,
        Query(alias="status"),
    ] = None,
) -> CalendarSyncOperationsListResponse:
    """Return a tenant-admin view of current and recent calendar delivery."""
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError("Application settings are unavailable.")

    page = await list_calendar_sync_operations(
        session,
        context=context,
        worker_heartbeat_max_age_seconds=(settings.calendar_sync_worker_heartbeat_max_age_seconds),
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return CalendarSyncOperationsListResponse(
        items=[CalendarSyncOperationItemResponse.model_validate(item) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        worker_available=page.worker_available,
        worker_last_seen_at=page.worker_last_seen_at,
    )


@router.post(
    "/{interview_session_id}/retry",
    response_model=InterviewCalendarSyncRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed calendar delivery as workspace administrator",
)
async def retry_calendar_sync_endpoint(
    interview_session_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewCalendarSyncRetryResponse:
    """Queue failed calendar sync work from the administrator monitor."""
    try:
        await retry_calendar_sync_as_admin(
            session,
            context=context,
            interview_session_id=interview_session_id,
        )
    except CalendarSyncRetryAlreadyQueuedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A calendar synchronization retry is already queued.",
        ) from error
    except CalendarSyncRetryUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There are no failed connected calendars to retry.",
        ) from error

    response.headers["Cache-Control"] = "private, no-store"
    return InterviewCalendarSyncRetryResponse()
