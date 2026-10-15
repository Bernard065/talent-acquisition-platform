"""Tenant-admin calendar synchronization monitoring and recovery operations."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.identity import User
from app.db.models.interview import InterviewSession
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.db.models.worker_heartbeat import WorkerHeartbeat
from app.db.transactions import transactional
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
    InterviewCalendarSyncStatus,
)
from app.domains.outbox.enums import OutboxEventStatus
from app.services.audit import record_audit_event
from app.services.interview_calendar_sync import (
    retry_failed_interview_calendar_syncs,
)
from app.services.outbox_inspection_errors import OutboxInspectionAccessDeniedError
from app.services.worker_heartbeats import CALENDAR_SYNC_WORKER_NAME

_CALENDAR_SYNC_EVENT = "interview.calendar_sync_requested"


@dataclass(frozen=True, slots=True)
class CalendarSyncOperationItem:
    """Safe operational fields for one interview calendar connection."""

    id: UUID
    interview_session_id: UUID
    interview_title: str
    scheduled_start_at: datetime
    calendar_owner_display_name: str
    provider: CalendarProvider
    connection_status: CalendarConnectionStatus
    sync_status: InterviewCalendarSyncStatus
    outbox_status: OutboxEventStatus | None
    attempts: int
    last_error_code: str | None
    last_attempt_at: datetime | None
    synced_at: datetime | None
    can_retry: bool


@dataclass(frozen=True, slots=True)
class CalendarSyncOperationsPage:
    """Paginated tenant calendar sync view and worker health."""

    items: tuple[CalendarSyncOperationItem, ...]
    total: int
    limit: int
    offset: int
    worker_available: bool
    worker_last_seen_at: datetime | None


def _require_tenant_admin(context: TenantContext) -> None:
    if Role.TENANT_ADMIN not in context.roles:
        raise OutboxInspectionAccessDeniedError(
            "Only workspace administrators may manage calendar synchronization."
        )


async def list_calendar_sync_operations(
    session: AsyncSession,
    *,
    context: TenantContext,
    worker_heartbeat_max_age_seconds: int,
    limit: int = 50,
    offset: int = 0,
    status_filter: InterviewCalendarSyncStatus | None = None,
) -> CalendarSyncOperationsPage:
    """List recent tenant calendar deliveries without exposing secrets or PII."""
    _require_tenant_admin(context)
    conditions = [InterviewCalendarSync.tenant_id == context.tenant_id]
    if status_filter is not None:
        conditions.append(InterviewCalendarSync.status == status_filter)

    total = await session.scalar(
        select(count(InterviewCalendarSync.id)).where(*conditions)
    )
    rows = await session.execute(
        select(
            InterviewCalendarSync,
            InterviewSession.scheduled_start_at,
            Requisition.title,
            User.display_name,
            CalendarConnection.status,
            CalendarConnection.provider,
        )
        .join(
            InterviewSession,
            (InterviewSession.id == InterviewCalendarSync.interview_session_id)
            & (InterviewSession.tenant_id == InterviewCalendarSync.tenant_id),
        )
        .join(
            Application,
            (Application.id == InterviewSession.application_id)
            & (Application.tenant_id == InterviewSession.tenant_id),
        )
        .join(
            Requisition,
            (Requisition.id == Application.requisition_id)
            & (Requisition.tenant_id == Application.tenant_id),
        )
        .join(
            CalendarConnection,
            (CalendarConnection.id == InterviewCalendarSync.calendar_connection_id)
            & (CalendarConnection.tenant_id == InterviewCalendarSync.tenant_id),
        )
        .join(
            User,
            (User.id == CalendarConnection.owner_user_id)
            & (User.tenant_id == CalendarConnection.tenant_id),
        )
        .where(*conditions)
        .order_by(InterviewCalendarSync.updated_at.desc(), InterviewCalendarSync.id.desc())
        .offset(offset)
        .limit(limit)
    )
    result_rows = list(rows.all())
    interview_ids = {str(row[0].interview_session_id) for row in result_rows}
    outbox_by_interview: dict[str, OutboxEvent] = {}
    if interview_ids:
        events = await session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.tenant_id == context.tenant_id,
                OutboxEvent.event_type == _CALENDAR_SYNC_EVENT,
                OutboxEvent.aggregate_id.in_(interview_ids),
            )
            .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
        )
        for event in events:
            outbox_by_interview.setdefault(event.aggregate_id, event)

    last_seen_at = await session.scalar(
        select(WorkerHeartbeat.last_heartbeat_at).where(
            WorkerHeartbeat.worker_name == CALENDAR_SYNC_WORKER_NAME,
        )
    )
    is_worker_available = bool(
        last_seen_at is not None
        and last_seen_at >= datetime.now(UTC) - timedelta(seconds=worker_heartbeat_max_age_seconds)
    )

    items: list[CalendarSyncOperationItem] = []
    for sync, scheduled_start, title, owner_name, connection_status, provider in result_rows:
        latest_event = outbox_by_interview.get(str(sync.interview_session_id))
        items.append(
            CalendarSyncOperationItem(
                id=sync.id,
                interview_session_id=sync.interview_session_id,
                interview_title=title,
                scheduled_start_at=scheduled_start,
                calendar_owner_display_name=owner_name,
                provider=provider,
                connection_status=connection_status,
                sync_status=sync.status,
                outbox_status=(latest_event.status if latest_event is not None else None),
                attempts=latest_event.attempts if latest_event is not None else 0,
                last_error_code=(
                    sync.last_error_code
                    or (latest_event.last_error if latest_event is not None else None)
                ),
                last_attempt_at=sync.last_attempt_at,
                synced_at=sync.synced_at,
                can_retry=(
                    sync.status is InterviewCalendarSyncStatus.FAILED
                    and connection_status is CalendarConnectionStatus.ACTIVE
                ),
            )
        )

    return CalendarSyncOperationsPage(
        items=tuple(items),
        total=total or 0,
        limit=limit,
        offset=offset,
        worker_available=is_worker_available,
        worker_last_seen_at=last_seen_at,
    )


async def retry_calendar_sync_as_admin(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
) -> None:
    """Allow workspace administrators to requeue a failed interview delivery."""
    _require_tenant_admin(context)
    async with transactional(session):
        await retry_failed_interview_calendar_syncs(
            session,
            context=context,
            interview_session_id=interview_session_id,
        )
        record_audit_event(
            session,
            context=context,
            action="calendar_sync.retry_requested",
            entity_type="interview_session",
            entity_id=str(interview_session_id),
        )
