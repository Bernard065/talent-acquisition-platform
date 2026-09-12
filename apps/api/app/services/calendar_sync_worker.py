"""Outbox-driven, retry-safe synchronization of interview calendar events."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.outbox import OutboxEvent
from app.db.transactions import transactional
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
    InterviewCalendarSyncStatus,
)
from app.domains.interviews.enums import InterviewSessionStatus
from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    CalendarCredentialResolver,
)
from app.services.calendar_provider import (
    CalendarEventDeletion,
    CalendarEventProvider,
    CalendarEventUpsert,
    CalendarProviderError,
)
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

_CALENDAR_SYNC_REQUESTED_EVENT = "interview.calendar_sync_requested"
_FAILURE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")

CalendarOperation = Literal["upsert", "cancel", "noop"]


@dataclass(frozen=True, slots=True)
class CalendarSyncWorkerResult:
    """Outcome of one bounded calendar-sync worker cycle."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class CalendarSyncRequest:
    """Validated, non-sensitive calendar synchronization event payload."""

    interview_session_id: UUID
    operation: Literal["upsert", "cancel"]
    interview_version: int


@dataclass(frozen=True, slots=True)
class PreparedCalendarSync:
    """Current database state needed for one provider operation."""

    sync_id: UUID
    tenant_id: UUID
    connection_id: UUID
    provider: CalendarProvider
    credential_reference: str
    external_calendar_id: str | None
    external_event_id: str | None
    external_idempotency_key: str
    interview_session_id: UUID
    interview_version: int
    starts_at: datetime
    ends_at: datetime
    operation: CalendarOperation


def _now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(UTC)


def _safe_failure_code(code: str) -> str:
    """Keep worker and outbox error classifications non-sensitive and valid."""
    normalized = code.strip().lower()

    if _FAILURE_CODE_PATTERN.fullmatch(normalized):
        return normalized

    return "calendar_sync_failed"


def _request_from_event(event: OutboxEvent) -> CalendarSyncRequest:
    """Parse the strictly limited calendar synchronization event payload."""
    payload = event.payload

    interview_session_id = UUID(str(payload["interview_session_id"]))
    operation = str(payload["operation"])
    interview_version = int(payload["interview_version"])

    if operation not in {"upsert", "cancel"}:
        raise ValueError("Calendar operation must be upsert or cancel.")

    if interview_version < 1:
        raise ValueError("Interview version must be positive.")

    return CalendarSyncRequest(
        interview_session_id=interview_session_id,
        operation=cast(Literal["upsert", "cancel"], operation),
        interview_version=interview_version,
    )


def _operation_for_current_session(
    *,
    requested_operation: Literal["upsert", "cancel"],
    status: InterviewSessionStatus,
) -> CalendarOperation:
    """
    Reconcile using current database state rather than stale event payload state.

    A late upsert event must never recreate a cancelled interview. Completed
    sessions need no calendar mutation because the event is already historical.
    """
    if requested_operation == "cancel" or status is InterviewSessionStatus.CANCELLED:
        return "cancel"

    if status is InterviewSessionStatus.SCHEDULED:
        return "upsert"

    return "noop"


async def _get_or_create_sync_for_update(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    interview_session_id: UUID,
    connection_id: UUID,
    interview_version: int,
) -> InterviewCalendarSync:
    """Create or lock one connection/session sync record safely under concurrency."""
    created_id = await session.scalar(
        insert(InterviewCalendarSync)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            interview_session_id=interview_session_id,
            calendar_connection_id=connection_id,
            external_idempotency_key=str(uuid4()),
            desired_interview_version=interview_version,
            status=InterviewCalendarSyncStatus.PENDING,
        )
        .on_conflict_do_nothing(
            constraint="uq_interview_calendar_syncs_connection_session"
        )
        .returning(InterviewCalendarSync.id)
    )

    sync = await session.scalar(
        select(InterviewCalendarSync)
        .where(
            InterviewCalendarSync.tenant_id == tenant_id,
            InterviewCalendarSync.interview_session_id == interview_session_id,
            InterviewCalendarSync.calendar_connection_id == connection_id,
        )
        .with_for_update()
    )
    if sync is None:
        raise RuntimeError(
            "Calendar sync record could not be loaded after creation."
        )

    # `created_id` is intentionally read to make the insertion outcome explicit.
    _ = created_id

    sync.status = InterviewCalendarSyncStatus.PENDING
    sync.desired_interview_version = interview_version
    sync.last_error_code = None
    sync.last_attempt_at = _now()

    return sync


async def _prepare_calendar_syncs(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    request: CalendarSyncRequest,
) -> tuple[PreparedCalendarSync, ...]:
    """
    Prepare all active calendar connections for the interview's current state.

    The event payload version is not trusted for synchronization; it exists
    only for deduplication and observability. The current interview version
    becomes the desired version persisted on every sync record.
    """
    async with transactional(session):
        interview_session = await session.scalar(
            select(InterviewSession)
            .where(
                InterviewSession.id == request.interview_session_id,
                InterviewSession.tenant_id == event.tenant_id,
            )
            .with_for_update()
        )
        if interview_session is None:
            raise LookupError("Interview session no longer exists.")

        participant_user_ids = select(InterviewParticipant.user_id).where(
            InterviewParticipant.tenant_id == event.tenant_id,
            InterviewParticipant.interview_session_id == interview_session.id,
        )

        connections = list(
            await session.scalars(
                select(CalendarConnection)
                .where(
                    CalendarConnection.tenant_id == event.tenant_id,
                    CalendarConnection.status == CalendarConnectionStatus.ACTIVE,
                    CalendarConnection.owner_user_id.in_(participant_user_ids),
                )
                .order_by(CalendarConnection.id)
                .with_for_update()
            )
        )

        operation = _operation_for_current_session(
            requested_operation=request.operation,
            status=interview_session.status,
        )
        prepared: list[PreparedCalendarSync] = []

        for connection in connections:
            sync = await _get_or_create_sync_for_update(
                session,
                tenant_id=event.tenant_id,
                interview_session_id=interview_session.id,
                connection_id=connection.id,
                interview_version=interview_session.version,
            )

            prepared.append(
                PreparedCalendarSync(
                    sync_id=sync.id,
                    tenant_id=event.tenant_id,
                    connection_id=connection.id,
                    provider=connection.provider,
                    credential_reference=connection.credential_reference,
                    external_calendar_id=connection.external_calendar_id,
                    external_event_id=sync.external_event_id,
                    external_idempotency_key=sync.external_idempotency_key,
                    interview_session_id=interview_session.id,
                    interview_version=interview_session.version,
                    starts_at=interview_session.scheduled_start_at,
                    ends_at=interview_session.scheduled_end_at,
                    operation=operation,
                )
            )

        await session.flush()

    return tuple(prepared)


async def _mark_sync_succeeded(
    session: AsyncSession,
    *,
    prepared: PreparedCalendarSync,
    external_event_id: str | None,
) -> None:
    """Persist a completed provider operation without retaining provider output."""
    async with transactional(session):
        sync = await session.scalar(
            select(InterviewCalendarSync)
            .where(
                InterviewCalendarSync.id == prepared.sync_id,
                InterviewCalendarSync.tenant_id == prepared.tenant_id,
            )
            .with_for_update()
        )
        if sync is None:
            return

        sync.status = InterviewCalendarSyncStatus.SYNCED
        sync.synced_interview_version = prepared.interview_version
        sync.last_error_code = None
        sync.last_attempt_at = _now()
        sync.synced_at = _now()

        if external_event_id is not None:
            sync.external_event_id = external_event_id

        if prepared.operation == "cancel":
            sync.external_event_id = None

        await session.flush()


async def _mark_sync_failed(
    session: AsyncSession,
    *,
    prepared: PreparedCalendarSync,
    failure_code: str,
) -> None:
    """Persist only a short classified failure code, never provider details."""
    async with transactional(session):
        sync = await session.scalar(
            select(InterviewCalendarSync)
            .where(
                InterviewCalendarSync.id == prepared.sync_id,
                InterviewCalendarSync.tenant_id == prepared.tenant_id,
            )
            .with_for_update()
        )
        if sync is None:
            return

        sync.status = InterviewCalendarSyncStatus.FAILED
        sync.last_error_code = _safe_failure_code(failure_code)
        sync.last_attempt_at = _now()
        await session.flush()


async def _execute_prepared_sync(
    *,
    prepared: PreparedCalendarSync,
    credential_resolver: CalendarCredentialResolver,
    providers: Mapping[CalendarProvider, CalendarEventProvider],
) -> str | None:
    """Resolve credentials in memory and perform one idempotent provider action."""
    if prepared.operation == "noop":
        return None

    provider = providers.get(prepared.provider)
    if provider is None:
        raise CalendarProviderError(
            "calendar_provider_not_configured",
            retryable=False,
        )

    credentials = await credential_resolver.resolve(
        credential_reference=prepared.credential_reference,
    )

    if prepared.operation == "cancel":
        if prepared.external_event_id is None:
            return None

        await provider.delete_event(
            credentials=credentials,
            event=CalendarEventDeletion(
                calendar_connection_id=prepared.connection_id,
                interview_session_id=prepared.interview_session_id,
                external_calendar_id=prepared.external_calendar_id,
                external_event_id=prepared.external_event_id,
                idempotency_key=prepared.external_idempotency_key,
            ),
        )
        return None

    result = await provider.upsert_event(
        credentials=credentials,
        event=CalendarEventUpsert(
            calendar_connection_id=prepared.connection_id,
            interview_session_id=prepared.interview_session_id,
            external_calendar_id=prepared.external_calendar_id,
            external_event_id=prepared.external_event_id,
            idempotency_key=prepared.external_idempotency_key,
            starts_at=prepared.starts_at,
            ends_at=prepared.ends_at,
        ),
    )
    return result.external_event_id


async def process_interview_calendar_sync_events(
    session: AsyncSession,
    *,
    worker_id: str,
    credential_resolver: CalendarCredentialResolver,
    providers: Mapping[CalendarProvider, CalendarEventProvider],
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> CalendarSyncWorkerResult:
    """
    Claim and process a bounded batch of interview calendar-sync events.

    Provider operations are intentionally outside database transactions. Sync
    records and outbox leases make retries safe through stable idempotency keys.
    """
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=frozenset({_CALENDAR_SYNC_REQUESTED_EVENT}),
    )

    processed = 0
    retried = 0
    dead_lettered = 0

    for event in events:
        try:
            request = _request_from_event(event)
            prepared_syncs = await _prepare_calendar_syncs(
                session,
                event=event,
                request=request,
            )
        except (KeyError, TypeError, ValueError):
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="invalid_calendar_sync_event_payload",
            )
            dead_lettered += 1
            continue
        except LookupError:
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="calendar_interview_not_found",
            )
            dead_lettered += 1
            continue

        try:
            for prepared in prepared_syncs:
                external_event_id = await _execute_prepared_sync(
                    prepared=prepared,
                    credential_resolver=credential_resolver,
                    providers=providers,
                )
                await _mark_sync_succeeded(
                    session,
                    prepared=prepared,
                    external_event_id=external_event_id,
                )
        except (
            CalendarCredentialResolutionError,
            CalendarProviderError,
        ) as error:
            failure_code = _safe_failure_code(error.code)

            # Only the connection currently being processed is marked failed.
            if "prepared" in locals():
                await _mark_sync_failed(
                    session,
                    prepared=prepared,
                    failure_code=failure_code,
                )

            if error.retryable:
                await schedule_outbox_event_retry(
                    session,
                    event_id=event.id,
                    worker_id=worker_id,
                    failure_code=failure_code,
                    policy=policy,
                )
                retried += 1
            else:
                await dead_letter_outbox_event(
                    session,
                    event_id=event.id,
                    worker_id=worker_id,
                    failure_code=failure_code,
                )
                dead_lettered += 1
            continue

        await mark_outbox_event_processed(
            session,
            event_id=event.id,
            worker_id=worker_id,
        )
        processed += 1

    return CalendarSyncWorkerResult(
        claimed=len(events),
        processed=processed,
        retried=retried,
        dead_lettered=dead_lettered,
    )
