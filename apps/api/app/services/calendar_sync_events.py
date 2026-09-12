"""Transaction-safe publishing of interview calendar synchronization work."""

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.interview import InterviewSession
from app.services.outbox import enqueue_outbox_event

CalendarSyncOperation = Literal["upsert", "cancel"]

_CALENDAR_SYNC_REQUESTED_EVENT = "interview.calendar_sync_requested"


def enqueue_interview_calendar_sync(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session: InterviewSession,
    operation: CalendarSyncOperation,
) -> None:
    """
    Queue identifier-only calendar synchronization work in the caller transaction.

    Calendar workers must load the current interview and its eligible calendar
    connections from the database. The outbox payload deliberately excludes
    candidate data, participant details, interview title, and provider secrets.
    """
    interview_version = interview_session.version

    enqueue_outbox_event(
        session,
        context=context,
        event_type=_CALENDAR_SYNC_REQUESTED_EVENT,
        aggregate_type="interview_session",
        aggregate_id=str(interview_session.id),
        deduplication_key=(
            f"calendar-sync:{interview_session.id}:"
            f"{interview_version}:{operation}"
        ),
        payload={
            "interview_session_id": str(interview_session.id),
            "operation": operation,
            "interview_version": interview_version,
        },
    )
