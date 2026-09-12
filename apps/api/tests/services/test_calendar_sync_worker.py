"""PostgreSQL integration tests for the calendar-sync worker service."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.application import Application
from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.calendar.enums import (
    CalendarConnectionStatus,
    CalendarProvider,
    InterviewCalendarSyncStatus,
)
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.outbox.enums import OutboxEventStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    ResolvedCalendarCredentials,
)
from app.services.calendar_provider import (
    CalendarEventDeletion,
    CalendarEventReference,
    CalendarEventUpsert,
    CalendarProviderError,
)
from app.services.calendar_sync_worker import (
    process_interview_calendar_sync_events,
)
from app.services.outbox_worker import OutboxWorkerPolicy


@dataclass
class _FakeCredentialResolver:
    """In-memory credential resolver that never persists secret material."""

    error: CalendarCredentialResolutionError | None = None
    references: list[str] = field(default_factory=list)

    async def resolve(
        self,
        *,
        credential_reference: str,
    ) -> ResolvedCalendarCredentials:
        """Record the reference and return deterministic test credentials."""
        self.references.append(credential_reference)

        if self.error is not None:
            raise self.error

        return ResolvedCalendarCredentials(
            values={"access_token": SecretStr("test-access-token")}
        )


@dataclass
class _FakeCalendarProvider:
    """In-memory provider adapter recording idempotent requests."""

    provider: CalendarProvider = CalendarProvider.GOOGLE
    error: CalendarProviderError | None = None
    upserts: list[CalendarEventUpsert] = field(default_factory=list)
    deletions: list[CalendarEventDeletion] = field(default_factory=list)

    async def upsert_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventUpsert,
    ) -> CalendarEventReference:
        """Record an upsert request and return a deterministic event ID."""
        if self.error is not None:
            raise self.error

        assert credentials.required("access_token").get_secret_value()
        self.upserts.append(event)
        return CalendarEventReference(
            external_event_id=f"provider-event-{event.interview_session_id}"
        )

    async def delete_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventDeletion,
    ) -> None:
        """Record a deletion request for the fake provider."""
        if self.error is not None:
            raise self.error

        assert credentials.required("access_token").get_secret_value()
        self.deletions.append(event)


@dataclass(frozen=True, slots=True)
class _SeededCalendarWork:
    """Records created for one worker test scenario."""

    tenant_id: UUID
    connection_id: UUID
    interview_session_id: UUID
    outbox_event_id: UUID


def _policy() -> OutboxWorkerPolicy:
    """Use a small predictable worker policy for integration tests."""
    return OutboxWorkerPolicy(batch_size=10, max_attempts=2)


async def _seed_calendar_work(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    operation: str = "upsert",
    interview_status: InterviewSessionStatus = InterviewSessionStatus.SCHEDULED,
    event_version: int = 1,
    existing_external_event_id: str | None = None,
    enqueue_event: bool = True,
) -> _SeededCalendarWork:
    """Create one tenant-owned interview, connection, and optional sync event."""
    owner = User(
        tenant_id=tenant_id,
        external_subject=f"calendar-owner-{tenant_id.hex[:12]}",
        email=f"calendar-owner-{tenant_id.hex[:12]}@example.test",
        display_name="Calendar Owner",
    )
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Calendar Worker Tenant {tenant_id.hex[:12]}",
            slug=f"calendar-worker-{tenant_id.hex[:12]}",
        )
    )
    session.add(owner)
    await session.flush()

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Private Candidate",
        email=f"candidate-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"candidate-{tenant_id.hex[:12]}@example.test",
        source="employee_referral",
        source_metadata={"private": "metadata"},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="seed",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Private Interview Role",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="seed",
    )
    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.INTERVIEW,
        created_by_subject="seed",
    )
    session.add(application)
    await session.flush()

    start_at = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    end_at = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)

    interview_session = InterviewSession(
        tenant_id=tenant_id,
        application_id=application.id,
        scheduled_start_at=start_at,
        scheduled_end_at=end_at,
        status=interview_status,
        completed_at=(
            datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
            if interview_status is InterviewSessionStatus.COMPLETED
            else None
        ),
        cancelled_at=(
            datetime(2026, 9, 14, 8, 0, tzinfo=UTC)
            if interview_status is InterviewSessionStatus.CANCELLED
            else None
        ),
        cancelled_by_subject=(
            "seed"
            if interview_status is InterviewSessionStatus.CANCELLED
            else None
        ),
        cancellation_reason=(
            InterviewCancellationReason.OTHER
            if interview_status is InterviewSessionStatus.CANCELLED
            else None
        ),
        created_by_subject="seed",
    )
    session.add(interview_session)
    await session.flush()

    session.add(
        InterviewParticipant(
            tenant_id=tenant_id,
            interview_session_id=interview_session.id,
            user_id=owner.id,
            role=InterviewParticipantRole.INTERVIEWER,
            scheduled_time_range=Range(start_at, end_at, bounds="[)"),
        )
    )

    connection = CalendarConnection(
        tenant_id=tenant_id,
        owner_user_id=owner.id,
        provider=CalendarProvider.GOOGLE,
        status=CalendarConnectionStatus.ACTIVE,
        credential_reference=f"vault://calendar/{tenant_id}/{owner.id}",
        external_calendar_id="primary",
    )
    session.add(connection)
    await session.flush()

    if existing_external_event_id is not None:
        session.add(
            InterviewCalendarSync(
                tenant_id=tenant_id,
                interview_session_id=interview_session.id,
                calendar_connection_id=connection.id,
                status=InterviewCalendarSyncStatus.SYNCED,
                external_event_id=existing_external_event_id,
                external_idempotency_key=str(uuid4()),
                desired_interview_version=interview_session.version,
                synced_interview_version=interview_session.version,
            )
        )

    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type="interview.calendar_sync_requested",
        aggregate_type="interview_session",
        aggregate_id=str(interview_session.id),
        deduplication_key=f"calendar-test:{uuid4()}",
        payload={
            "interview_session_id": str(interview_session.id),
            "operation": operation,
            "interview_version": event_version,
        },
    )
    if enqueue_event:
        session.add(event)

    await session.commit()

    return _SeededCalendarWork(
        tenant_id=tenant_id,
        connection_id=connection.id,
        interview_session_id=interview_session.id,
        outbox_event_id=event.id,
    )


@pytest.mark.asyncio
async def test_upserts_current_interview_and_persists_privacy_safe_sync_state(
    session: AsyncSession,
) -> None:
    """Create one provider event and persist only opaque synchronization state."""
    seeded = await _seed_calendar_work(session, tenant_id=uuid4())
    resolver = _FakeCredentialResolver()
    provider = _FakeCalendarProvider()

    result = await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=resolver,
        providers={CalendarProvider.GOOGLE: provider},
        policy=_policy(),
    )

    sync = await session.scalar(
        select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_session_id
            == seeded.interview_session_id
        )
    )
    event = await session.get(OutboxEvent, seeded.outbox_event_id)

    assert result.claimed == 1
    assert result.processed == 1
    assert result.retried == 0
    assert result.dead_lettered == 0

    assert len(provider.upserts) == 1
    assert provider.upserts[0].interview_session_id == seeded.interview_session_id
    assert provider.upserts[0].title == "Interview"

    assert sync is not None
    assert sync.status is InterviewCalendarSyncStatus.SYNCED
    assert sync.external_event_id == (
        f"provider-event-{seeded.interview_session_id}"
    )
    assert sync.synced_interview_version == 1
    assert "test-access-token" not in repr(sync)
    assert not hasattr(sync, "credentials")
    assert not hasattr(sync, "access_token")

    assert event is not None
    assert event.status is OutboxEventStatus.PROCESSED
    assert event.payload == {
        "interview_session_id": str(seeded.interview_session_id),
        "operation": "upsert",
        "interview_version": 1,
    }


@pytest.mark.asyncio
async def test_cancellation_deletes_existing_provider_event(
    session: AsyncSession,
) -> None:
    """Cancellation deletes the external event and clears its stored reference."""
    seeded = await _seed_calendar_work(
        session,
        tenant_id=uuid4(),
        operation="cancel",
        interview_status=InterviewSessionStatus.CANCELLED,
        existing_external_event_id="google-event-123",
    )
    provider = _FakeCalendarProvider()

    result = await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=_FakeCredentialResolver(),
        providers={CalendarProvider.GOOGLE: provider},
        policy=_policy(),
    )

    sync = await session.scalar(
        select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_session_id
            == seeded.interview_session_id
        )
    )

    assert result.processed == 1
    assert len(provider.deletions) == 1
    assert provider.deletions[0].external_event_id == "google-event-123"

    assert sync is not None
    assert sync.status is InterviewCalendarSyncStatus.SYNCED
    assert sync.external_event_id is None
    assert sync.synced_interview_version == 1


@pytest.mark.asyncio
async def test_stale_event_uses_current_interview_version_and_interval(
    session: AsyncSession,
) -> None:
    """A delayed outbox event synchronizes current database state, not its payload."""
    seeded = await _seed_calendar_work(
        session,
        tenant_id=uuid4(),
        event_version=1,
    )
    interview_session = await session.get(
        InterviewSession,
        seeded.interview_session_id,
    )
    assert interview_session is not None

    current_start = datetime(2026, 9, 14, 13, 0, tzinfo=UTC)
    current_end = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
    interview_session.scheduled_start_at = current_start
    interview_session.scheduled_end_at = current_end
    await session.commit()

    provider = _FakeCalendarProvider()
    await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=_FakeCredentialResolver(),
        providers={CalendarProvider.GOOGLE: provider},
        policy=_policy(),
    )

    sync = await session.scalar(
        select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_session_id
            == seeded.interview_session_id
        )
    )

    assert len(provider.upserts) == 1
    assert provider.upserts[0].starts_at == current_start
    assert provider.upserts[0].ends_at == current_end

    assert sync is not None
    assert sync.desired_interview_version == 2
    assert sync.synced_interview_version == 2


@pytest.mark.asyncio
async def test_retryable_provider_outage_marks_sync_failed_and_retries_event(
    session: AsyncSession,
) -> None:
    """Temporary provider failures preserve work for retry."""
    seeded = await _seed_calendar_work(session, tenant_id=uuid4())
    provider = _FakeCalendarProvider(
        error=CalendarProviderError(
            "calendar_provider_unavailable",
            retryable=True,
        )
    )

    result = await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=_FakeCredentialResolver(),
        providers={CalendarProvider.GOOGLE: provider},
        policy=_policy(),
    )

    sync = await session.scalar(
        select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_session_id
            == seeded.interview_session_id
        )
    )
    event = await session.get(OutboxEvent, seeded.outbox_event_id)

    assert result.processed == 0
    assert result.retried == 1
    assert result.dead_lettered == 0

    assert sync is not None
    assert sync.status is InterviewCalendarSyncStatus.FAILED
    assert sync.last_error_code == "calendar_provider_unavailable"

    assert event is not None
    assert event.status is OutboxEventStatus.PENDING
    assert event.last_error == "calendar_provider_unavailable"


@pytest.mark.asyncio
async def test_missing_provider_is_terminal_and_dead_letters_event(
    session: AsyncSession,
) -> None:
    """Missing adapter configuration is a terminal, inspectable failure."""
    seeded = await _seed_calendar_work(session, tenant_id=uuid4())

    result = await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=_FakeCredentialResolver(),
        providers={},
        policy=_policy(),
    )

    sync = await session.scalar(
        select(InterviewCalendarSync).where(
            InterviewCalendarSync.interview_session_id
            == seeded.interview_session_id
        )
    )
    event = await session.get(OutboxEvent, seeded.outbox_event_id)

    assert result.processed == 0
    assert result.retried == 0
    assert result.dead_lettered == 1

    assert sync is not None
    assert sync.status is InterviewCalendarSyncStatus.FAILED
    assert sync.last_error_code == "calendar_provider_not_configured"

    assert event is not None
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "calendar_provider_not_configured"


@pytest.mark.asyncio
async def test_only_loads_calendar_connections_for_event_tenant(
    session: AsyncSession,
) -> None:
    """A tenant's event must never create work for another tenant's connection."""
    seeded = await _seed_calendar_work(session, tenant_id=uuid4())
    other_tenant = await _seed_calendar_work(
        session,
        tenant_id=uuid4(),
        enqueue_event=False,
    )
    provider = _FakeCalendarProvider()

    result = await process_interview_calendar_sync_events(
        session,
        worker_id="calendar-worker-test",
        credential_resolver=_FakeCredentialResolver(),
        providers={CalendarProvider.GOOGLE: provider},
        policy=_policy(),
    )

    syncs = list(await session.scalars(select(InterviewCalendarSync)))

    assert result.processed == 1
    assert len(syncs) == 1
    assert syncs[0].tenant_id == seeded.tenant_id
    assert syncs[0].calendar_connection_id == seeded.connection_id
    assert syncs[0].calendar_connection_id != other_tenant.connection_id
