"""Read and retry interview calendar synchronization state."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.outbox import OutboxEvent
from app.db.models.worker_heartbeat import WorkerHeartbeat
from app.db.transactions import transactional
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    InterviewCalendarSyncStatus,
)
from app.domains.interviews.enums import InterviewSessionStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.calendar_sync_events import enqueue_interview_calendar_sync
from app.services.interview_lifecycle_errors import InterviewSessionNotFoundError
from app.services.interview_search import get_interview_session
from app.services.interview_search_errors import InterviewSearchAccessDeniedError
from app.services.worker_heartbeats import CALENDAR_SYNC_WORKER_NAME

_CALENDAR_SYNC_EVENT = "interview.calendar_sync_requested"
_CALENDAR_SYNC_READ_ROLES = frozenset(
    {Role.TENANT_ADMIN, Role.RECRUITER, Role.PEOPLE_OPERATIONS}
)


def can_retry_interview_calendar_sync(context: TenantContext) -> bool:
    """Return whether the caller may trigger tenant-wide calendar retries."""
    return not context.roles.isdisjoint(_CALENDAR_SYNC_READ_ROLES)


class CalendarSyncRetryUnavailableError(Exception):
    """Raised when no failed, connected calendar sync is available to retry."""


class CalendarSyncRetryAlreadyQueuedError(Exception):
    """Raised when a retry is already pending or being processed."""


@dataclass(frozen=True, slots=True)
class InterviewCalendarSyncSnapshot:
    """Safe per-interview sync state and worker/queue diagnostics."""

    rows: list[tuple[InterviewCalendarSync | None, CalendarConnection, str]]
    queue_status: OutboxEventStatus | None
    queued_at: datetime | None
    worker_last_seen_at: datetime | None
    worker_available: bool
    interview_version: int


async def get_interview_calendar_sync_snapshot(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    worker_heartbeat_max_age_seconds: int,
) -> InterviewCalendarSyncSnapshot:
    """Get sync rows with queue and durable worker-liveness diagnostics."""
    interview = await get_interview_session(
        session,
        context=context,
        interview_session_id=interview_session_id,
    )

    rows = await session.execute(
        select(InterviewCalendarSync, CalendarConnection, User.display_name)
        .select_from(InterviewSession)
        .join(
            InterviewParticipant,
            and_(
                InterviewParticipant.interview_session_id == InterviewSession.id,
                InterviewParticipant.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .join(
            CalendarConnection,
            and_(
                CalendarConnection.owner_user_id == InterviewParticipant.user_id,
                CalendarConnection.tenant_id == InterviewParticipant.tenant_id,
            ),
        )
        .join(
            User,
            (User.id == CalendarConnection.owner_user_id)
            & (User.tenant_id == CalendarConnection.tenant_id),
        )
        .outerjoin(
            InterviewCalendarSync,
            and_(
                InterviewCalendarSync.calendar_connection_id == CalendarConnection.id,
                InterviewCalendarSync.interview_session_id == InterviewSession.id,
                InterviewCalendarSync.tenant_id == InterviewSession.tenant_id,
            ),
        )
        .where(
            InterviewSession.id == interview_session_id,
            InterviewSession.tenant_id == context.tenant_id,
            or_(
                CalendarConnection.status == CalendarConnectionStatus.ACTIVE,
                InterviewCalendarSync.id.is_not(None),
            ),
        )
        .order_by(User.display_name, CalendarConnection.provider)
    )
    queue_event = await session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.tenant_id == context.tenant_id,
            OutboxEvent.event_type == _CALENDAR_SYNC_EVENT,
            OutboxEvent.aggregate_id == str(interview_session_id),
        )
        .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
        .limit(1)
    )
    worker_last_seen_at = await session.scalar(
        select(WorkerHeartbeat.last_heartbeat_at).where(
            WorkerHeartbeat.worker_name == CALENDAR_SYNC_WORKER_NAME,
        )
    )
    worker_available = bool(
        worker_last_seen_at is not None
        and worker_last_seen_at
        >= datetime.now(UTC)
        - timedelta(seconds=worker_heartbeat_max_age_seconds)
    )
    return InterviewCalendarSyncSnapshot(
        rows=[(sync, connection, display_name) for sync, connection, display_name in rows],
        queue_status=queue_event.status if queue_event is not None else None,
        queued_at=queue_event.created_at if queue_event is not None else None,
        worker_last_seen_at=worker_last_seen_at,
        worker_available=worker_available,
        interview_version=interview.version,
    )


async def retry_failed_interview_calendar_syncs(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
) -> None:
    """Queue one safe retry for active participant calendars in failed state."""
    if not can_retry_interview_calendar_sync(context):
        raise InterviewSearchAccessDeniedError(
            "Caller is not permitted to retry calendar synchronization."
        )

    await get_interview_session(
        session,
        context=context,
        interview_session_id=interview_session_id,
    )

    async with transactional(session):
        interview = await session.scalar(
            select(InterviewSession)
            .where(
                InterviewSession.id == interview_session_id,
                InterviewSession.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if interview is None:
            raise InterviewSessionNotFoundError("Interview session was not found.")

        failed_syncs = list(
            await session.scalars(
                select(InterviewCalendarSync)
                .join(
                    CalendarConnection,
                    (CalendarConnection.id == InterviewCalendarSync.calendar_connection_id)
                    & (CalendarConnection.tenant_id == InterviewCalendarSync.tenant_id),
                )
                .where(
                    InterviewCalendarSync.tenant_id == context.tenant_id,
                    InterviewCalendarSync.interview_session_id == interview.id,
                    InterviewCalendarSync.status == InterviewCalendarSyncStatus.FAILED,
                    CalendarConnection.status == CalendarConnectionStatus.ACTIVE,
                )
                .with_for_update(of=InterviewCalendarSync)
            )
        )
        if not failed_syncs:
            raise CalendarSyncRetryUnavailableError

        queued_event = await session.scalar(
            select(OutboxEvent.id).where(
                OutboxEvent.tenant_id == context.tenant_id,
                OutboxEvent.event_type == _CALENDAR_SYNC_EVENT,
                OutboxEvent.aggregate_id == str(interview.id),
                OutboxEvent.status.in_(
                    [OutboxEventStatus.PENDING, OutboxEventStatus.PROCESSING]
                ),
            ).limit(1)
        )
        if queued_event is not None:
            raise CalendarSyncRetryAlreadyQueuedError

        operation: Literal["upsert", "cancel"] = (
            "cancel"
            if interview.status is InterviewSessionStatus.CANCELLED
            else "upsert"
        )
        enqueue_interview_calendar_sync(
            session,
            context=context,
            interview_session=interview,
            operation=operation,
            retry_id=uuid4(),
        )
        for sync in failed_syncs:
            sync.status = InterviewCalendarSyncStatus.PENDING
            sync.last_error_code = None

        await session.flush()
