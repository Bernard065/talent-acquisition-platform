"""Version 1 private interview calendar search endpoint."""

from datetime import datetime
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session, get_tenant_context
from app.api.v1.schemas.interviews import (
    InterviewCalendarSyncListResponse,
    InterviewCalendarSyncResponse,
    InterviewCalendarSyncRetryResponse,
    InterviewSearchListResponse,
    InterviewSearchResultResponse,
    InterviewSessionResponse,
)
from app.core.authorization import TenantContext
from app.core.config import Settings
from app.db.models.calendar import InterviewCalendarSync
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    InterviewCalendarSyncStatus,
)
from app.domains.interviews.enums import InterviewSessionStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.interview_calendar_sync import (
    CalendarSyncRetryAlreadyQueuedError,
    CalendarSyncRetryUnavailableError,
    can_retry_interview_calendar_sync,
    get_interview_calendar_sync_snapshot,
    retry_failed_interview_calendar_syncs,
)
from app.services.interview_search import (
    InterviewSearchFilters,
    get_interview_session,
    search_interviews,
)

router = APIRouter(prefix="/interviews", tags=["Interviews"])

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _calendar_delivery_state(
    *,
    sync: InterviewCalendarSync | None,
    connection_status: CalendarConnectionStatus,
    queue_status: OutboxEventStatus | None,
    worker_available: bool,
    interview_version: int,
) -> Literal[
    "queued",
    "syncing",
    "synced",
    "failed",
    "disabled",
    "worker_unavailable",
    "not_queued",
]:
    """Describe the current delivery lifecycle in recruiter-friendly terms."""
    if connection_status is CalendarConnectionStatus.DISABLED:
        return "disabled"
    if sync is not None and sync.status is InterviewCalendarSyncStatus.FAILED:
        return "failed"
    if queue_status is OutboxEventStatus.DEAD_LETTERED:
        return "failed"
    if queue_status is OutboxEventStatus.PENDING:
        return "queued" if worker_available else "worker_unavailable"
    if queue_status is OutboxEventStatus.PROCESSING:
        return "syncing" if worker_available else "worker_unavailable"
    if (
        sync is not None
        and sync.status is InterviewCalendarSyncStatus.SYNCED
        and sync.synced_interview_version == interview_version
    ):
        return "synced"
    if sync is not None and sync.status is InterviewCalendarSyncStatus.DISABLED:
        return "disabled"
    if sync is not None and sync.status is InterviewCalendarSyncStatus.PENDING:
        return "not_queued" if worker_available else "worker_unavailable"
    return "not_queued"


@router.get(
    "/{interview_session_id}/calendar-syncs",
    response_model=InterviewCalendarSyncListResponse,
    summary="Get interview calendar synchronization status",
)
async def list_interview_calendar_syncs_endpoint(
    interview_session_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    request: Request,
) -> InterviewCalendarSyncListResponse:
    """Return safe synchronization state for calendars on this interview."""
    settings = cast(Settings, request.app.state.settings)
    snapshot = await get_interview_calendar_sync_snapshot(
        session,
        context=context,
        interview_session_id=interview_session_id,
        worker_heartbeat_max_age_seconds=(
            settings.calendar_sync_worker_heartbeat_max_age_seconds
        ),
    )
    response.headers["Cache-Control"] = "private, no-store"
    return InterviewCalendarSyncListResponse(
        can_retry=can_retry_interview_calendar_sync(context),
        worker_available=snapshot.worker_available,
        worker_last_seen_at=snapshot.worker_last_seen_at,
        queue_status=snapshot.queue_status,
        queued_at=snapshot.queued_at,
        items=[
            InterviewCalendarSyncResponse(
                calendar_owner_display_name=display_name,
                provider=connection.provider,
                connection_status=connection.status,
                status=(
                    sync.status
                    if sync is not None
                    else InterviewCalendarSyncStatus.PENDING
                ),
                delivery_state=_calendar_delivery_state(
                    sync=sync,
                    connection_status=connection.status,
                    queue_status=snapshot.queue_status,
                    worker_available=snapshot.worker_available,
                    interview_version=snapshot.interview_version,
                ),
                last_error_code=sync.last_error_code if sync is not None else None,
                last_attempt_at=sync.last_attempt_at if sync is not None else None,
                synced_at=sync.synced_at if sync is not None else None,
            )
            for sync, connection, display_name in snapshot.rows
        ]
    )


@router.post(
    "/{interview_session_id}/calendar-syncs/retry",
    response_model=InterviewCalendarSyncRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed interview calendar synchronization",
)
async def retry_interview_calendar_syncs_endpoint(
    interview_session_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewCalendarSyncRetryResponse:
    """Queue a retry for failed participant calendar deliveries."""
    try:
        await retry_failed_interview_calendar_syncs(
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


@router.get(
    "/{interview_session_id}",
    response_model=InterviewSessionResponse,
    summary="Get one interview session",
)
async def get_interview_session_endpoint(
    interview_session_id: UUID,
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
) -> InterviewSessionResponse:
    """Return one interview visible to the caller without feedback content."""
    interview = await get_interview_session(
        session,
        context=context,
        interview_session_id=interview_session_id,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return InterviewSessionResponse.model_validate(interview)


@router.get(
    "",
    response_model=InterviewSearchListResponse,
    summary="Search interview schedule",
)
async def search_interviews_endpoint(
    context: CallerContext,
    session: DatabaseSession,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(max_length=512)] = None,
    application_id: UUID | None = None,
    participant_user_id: UUID | None = None,
    interview_status: Annotated[
        InterviewSessionStatus | None,
        Query(alias="status"),
    ] = None,
    scheduled_after: datetime | None = None,
    scheduled_before: datetime | None = None,
) -> InterviewSearchListResponse:
    """Return the caller-authorized tenant interview calendar."""
    page = await search_interviews(
        session,
        context=context,
        filters=InterviewSearchFilters(
            application_id=application_id,
            participant_user_id=participant_user_id,
            status=interview_status,
            scheduled_after=scheduled_after,
            scheduled_before=scheduled_before,
        ),
        limit=limit,
        cursor=cursor,
    )
    response.headers["Cache-Control"] = "private, no-store"

    return InterviewSearchListResponse(
        items=[
            InterviewSearchResultResponse.model_validate(interview)
            for interview in page.items
        ],
        next_cursor=page.next_cursor,
    )
