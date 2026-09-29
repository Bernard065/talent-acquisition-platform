"""PostgreSQL tests for retry-safe job-board event dispatch."""

import asyncio
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

import app.services.job_board_dispatch as dispatch_module
from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.job_board_publication import JobBoardPublication
from app.db.models.job_posting import JobPosting
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.job_boards.enums import JobBoardPublicationStatus
from app.domains.job_postings.enums import EmploymentType
from app.domains.outbox.enums import OutboxEventStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.services.job_board_dispatch import (
    JobBoardDispatchResult,
    dispatch_job_board_events,
)
from app.services.job_board_provider import (
    JobBoardProviderError,
    PublishedJobBoardListing,
    PublishJobBoardListingCommand,
    UnpublishJobBoardListingCommand,
)
from app.services.job_board_publications import (
    request_job_board_publication,
    request_job_board_unpublication,
)
from app.services.job_postings import (
    CreateJobPostingCommand,
    create_job_posting,
    publish_job_posting,
)
from app.services.outbox_worker import OutboxWorkerPolicy


class FakeJobBoardProvider:
    """Record calls and return deterministic results without network access."""

    provider_key = "board_a"

    def __init__(self) -> None:
        self.publish_commands: list[PublishJobBoardListingCommand] = []
        self.unpublish_commands: list[UnpublishJobBoardListingCommand] = []
        self.publish_error: JobBoardProviderError | None = None
        self.publish_entered: asyncio.Event | None = None
        self.publish_release: asyncio.Event | None = None

    async def publish(
        self,
        *,
        command: PublishJobBoardListingCommand,
    ) -> PublishedJobBoardListing:
        self.publish_commands.append(command)
        if self.publish_entered is not None:
            self.publish_entered.set()
        if self.publish_release is not None:
            await self.publish_release.wait()
        if self.publish_error is not None:
            raise self.publish_error
        return PublishedJobBoardListing(external_posting_id="remote-listing-42")

    async def unpublish(
        self,
        *,
        command: UnpublishJobBoardListingCommand,
    ) -> None:
        self.unpublish_commands.append(command)


def _context(tenant_id: UUID) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject="job-board-dispatch-test-user",
        roles=frozenset({Role.RECRUITER}),
        request_id="job-board-dispatch-test-request",
    )


async def _seed_publication(
    session: AsyncSession,
    *,
    provider_key: str = "board_a",
) -> tuple[TenantContext, JobPosting, JobBoardPublication]:
    """Create a tenant-owned, locally published posting and queue its dispatch."""
    tenant_id = uuid4()
    context = _context(tenant_id)
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Dispatch Tenant {tenant_id.hex[:12]}",
            slug=f"dispatch-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Public Software Engineer",
        description="Public role description",
        department="Engineering",
        location="Nairobi",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject=context.subject,
    )
    session.add(requisition)
    await session.commit()

    draft = await create_job_posting(
        session,
        context=context,
        requisition_id=requisition.id,
        command=CreateJobPostingCommand(employment_type=EmploymentType.FULL_TIME),
    )
    posting = await publish_job_posting(
        session,
        context=context,
        job_posting_id=draft.id,
        expected_version=draft.version,
    )
    publication = await request_job_board_publication(
        session,
        context=context,
        job_posting_id=posting.id,
        provider_key=provider_key,
    )
    await session.flush()
    return context, posting, publication


async def _event_for(
    session: AsyncSession,
    publication: JobBoardPublication,
    event_type: str = "job_board.publish_requested",
) -> OutboxEvent:
    event = await session.scalar(
        select(OutboxEvent)
        .where(
            OutboxEvent.aggregate_id == str(publication.id),
            OutboxEvent.event_type == event_type,
        )
        .order_by(OutboxEvent.created_at)
    )
    assert event is not None
    return event


@pytest.mark.asyncio
async def test_publish_dispatch_persists_safe_result_and_stable_idempotency_key(
    session: AsyncSession,
) -> None:
    """Publish only the public snapshot and atomically persist safe outcome data."""
    context, posting, publication = await _seed_publication(session)
    event = await _event_for(session, publication)
    provider = FakeJobBoardProvider()

    result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )

    await session.refresh(publication)
    await session.refresh(event)
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == context.tenant_id,
                AuditEvent.entity_id == str(publication.id),
                AuditEvent.action == "job_board.publication.synchronized",
            )
        )
    )
    assert result.claimed == result.processed == 1
    assert result.retried == result.dead_lettered == 0
    assert len(provider.publish_commands) == 1
    command = provider.publish_commands[0]
    assert command.public_id == posting.public_id
    assert command.slug == posting.slug
    assert command.title == posting.title
    assert command.description == posting.description
    assert command.idempotency_key == str(event.id)
    assert {field.name for field in fields(command)} == {
        "public_id",
        "slug",
        "title",
        "description",
        "department",
        "location",
        "employment_type",
        "expires_at",
        "external_posting_id",
        "idempotency_key",
    }
    assert publication.status is JobBoardPublicationStatus.PUBLISHED
    assert publication.external_posting_id == "remote-listing-42"
    assert publication.dispatch_locked_by is None
    assert publication.dispatch_locked_until is None
    assert event.status is OutboxEventStatus.PROCESSED
    assert len(audits) == 1
    assert set(audits[0].details or {}) == {
        "provider_key",
        "operation",
        "generation",
    }
    assert posting.title not in str(event.payload)
    assert posting.description not in str(event.payload)
    assert posting.title not in str(audits[0].details)
    assert posting.description not in str(audits[0].details)


@pytest.mark.asyncio
async def test_unpublish_dispatch_uses_stored_remote_reference(
    session: AsyncSession,
) -> None:
    """An unpublish reaches the provider only with its persisted remote ID."""
    context, _, publication = await _seed_publication(session)
    provider = FakeJobBoardProvider()
    await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )
    await request_job_board_unpublication(
        session,
        context=context,
        publication_id=publication.id,
    )
    event = await _event_for(
        session,
        publication,
        event_type="job_board.unpublish_requested",
    )

    result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )

    await session.refresh(publication)
    await session.refresh(event)
    assert result.processed == 1
    assert publication.status is JobBoardPublicationStatus.UNPUBLISHED
    assert publication.external_posting_id == "remote-listing-42"
    assert len(provider.unpublish_commands) == 1
    assert provider.unpublish_commands[0].external_posting_id == "remote-listing-42"
    assert provider.unpublish_commands[0].idempotency_key == str(event.id)
    assert event.status is OutboxEventStatus.PROCESSED


@pytest.mark.asyncio
async def test_retryable_and_terminal_provider_errors_are_safely_classified(
    session: AsyncSession,
) -> None:
    """Retryable failures retry; terminal failures dead-letter without raw text."""
    _, _, publication = await _seed_publication(session)
    event = await _event_for(session, publication)
    provider = FakeJobBoardProvider()
    provider.publish_error = JobBoardProviderError(
        "credential=do-not-persist", retryable=True
    )

    retry_result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
        policy=OutboxWorkerPolicy(base_retry_delay=timedelta(seconds=1)),
    )
    await session.refresh(publication)
    await session.refresh(event)
    assert retry_result.retried == 1
    assert event.status is OutboxEventStatus.PENDING
    assert event.last_error == "provider_retryable_error"
    assert publication.last_error_code == "provider_retryable_error"
    assert "do-not-persist" not in str(event.last_error)
    assert "do-not-persist" not in str(publication.last_error_code)

    event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    provider.publish_error = JobBoardProviderError(
        "provider rejected request", retryable=False
    )
    terminal_result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )
    await session.refresh(publication)
    await session.refresh(event)
    assert terminal_result.dead_lettered == 1
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "provider_terminal_error"
    assert publication.status is JobBoardPublicationStatus.FAILED
    assert publication.last_error_code == "provider_terminal_error"


@pytest.mark.asyncio
async def test_missing_provider_dead_letters_without_calling_external_service(
    session: AsyncSession,
) -> None:
    """A board adapter not configured in this process is a terminal condition."""
    _, _, publication = await _seed_publication(session)
    event = await _event_for(session, publication)

    result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={},
    )

    await session.refresh(publication)
    await session.refresh(event)
    assert result.dead_lettered == 1
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.last_error == "provider_not_configured"
    assert publication.status is JobBoardPublicationStatus.FAILED


@pytest.mark.asyncio
async def test_slow_provider_times_out_before_publication_lease_expires(
    session: AsyncSession,
) -> None:
    """A stuck provider is cancelled and safely returned to the retry queue."""
    _, _, publication = await _seed_publication(session)
    event = await _event_for(session, publication)
    provider = FakeJobBoardProvider()
    provider.publish_entered = asyncio.Event()
    provider.publish_release = asyncio.Event()

    result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
        policy=OutboxWorkerPolicy(
            visibility_timeout=timedelta(milliseconds=250),
            base_retry_delay=timedelta(seconds=1),
        ),
    )

    await session.refresh(publication)
    await session.refresh(event)
    assert result.retried == 1
    assert provider.publish_entered.is_set()
    assert event.status is OutboxEventStatus.PENDING
    assert event.last_error == "provider_timeout"
    assert publication.dispatch_locked_by is None


@pytest.mark.asyncio
async def test_stale_first_attempt_is_acknowledged_without_publishing(
    session: AsyncSession,
) -> None:
    """A superseded first-attempt publish is skipped before touching the provider."""
    context, _, publication = await _seed_publication(session)
    publish_event = await _event_for(session, publication)
    await request_job_board_unpublication(
        session,
        context=context,
        publication_id=publication.id,
    )
    unpublish_event = await _event_for(
        session,
        publication,
        event_type="job_board.unpublish_requested",
    )
    unpublish_event.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
    provider = FakeJobBoardProvider()

    result = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
        policy=OutboxWorkerPolicy(batch_size=1),
    )

    await session.refresh(publish_event)
    await session.refresh(publication)
    assert result.processed == 1
    assert publish_event.status is OutboxEventStatus.PROCESSED
    assert provider.publish_commands == []
    assert publication.status is JobBoardPublicationStatus.UNPUBLISH_REQUESTED


@pytest.mark.asyncio
async def test_stale_retry_cannot_unpublish_a_newer_successful_publication(
    session: AsyncSession,
) -> None:
    """A late retry of generation N cannot undo an already-synced generation N+1."""
    context, _, publication = await _seed_publication(session)
    provider = FakeJobBoardProvider()

    first_publish = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )
    assert first_publish.processed == 1

    await request_job_board_unpublication(
        session,
        context=context,
        publication_id=publication.id,
    )
    old_unpublish = await _event_for(
        session,
        publication,
        event_type="job_board.unpublish_requested",
    )
    old_unpublish.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)
    await request_job_board_publication(
        session,
        context=context,
        job_posting_id=publication.job_posting_id,
        provider_key=publication.provider_key,
    )
    await session.commit()

    republish = await dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )
    await session.refresh(publication)
    assert republish.processed == 1
    assert publication.status is JobBoardPublicationStatus.PUBLISHED
    assert publication.last_synced_generation == publication.desired_generation

    old_unpublish.attempts = 1
    old_unpublish.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    late_retry = await dispatch_job_board_events(
        session,
        worker_id="job-board-recovery-worker",
        providers={provider.provider_key: provider},
    )
    await session.refresh(publication)
    await session.refresh(old_unpublish)
    assert late_retry.processed == 1
    assert old_unpublish.status is OutboxEventStatus.PROCESSED
    assert publication.status is JobBoardPublicationStatus.PUBLISHED
    assert publication.last_synced_generation == publication.desired_generation
    assert len(provider.publish_commands) == 2
    assert provider.unpublish_commands == []


@pytest.mark.asyncio
async def test_provider_success_is_recovered_after_outbox_ack_failure(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redelivery safely acknowledges after provider success and local commit."""
    _, _, publication = await _seed_publication(session)
    event = await _event_for(session, publication)
    provider = FakeJobBoardProvider()

    original_ack = dispatch_module.mark_outbox_event_processed

    async def fail_ack_once(*args: object, **kwargs: object) -> OutboxEvent:
        raise RuntimeError("simulated acknowledgement outage")

    monkeypatch.setattr(dispatch_module, "mark_outbox_event_processed", fail_ack_once)
    first = await dispatch_module.dispatch_job_board_events(
        session,
        worker_id="job-board-worker-test",
        providers={provider.provider_key: provider},
    )
    await session.refresh(publication)
    await session.refresh(event)
    assert first.retried == 1
    assert publication.status is JobBoardPublicationStatus.PUBLISHED
    assert publication.external_posting_id == "remote-listing-42"
    assert event.status is OutboxEventStatus.PROCESSING

    monkeypatch.setattr(dispatch_module, "mark_outbox_event_processed", original_ack)
    event.locked_at = datetime.now(UTC) - timedelta(hours=1)
    await session.flush()
    second = await dispatch_job_board_events(
        session,
        worker_id="job-board-recovery-worker",
        providers={provider.provider_key: provider},
        policy=OutboxWorkerPolicy(visibility_timeout=timedelta(seconds=30)),
    )
    await session.refresh(event)
    assert second.processed == 1
    assert event.status is OutboxEventStatus.PROCESSED
    assert len(provider.publish_commands) == 1


@pytest.mark.asyncio
async def test_publication_lease_serializes_stale_retry_and_new_unpublish(
    session: AsyncSession,
    database_engine: AsyncEngine,
) -> None:
    """An old retry cannot race a newer unpublish provider operation."""
    context, _, publication = await _seed_publication(session)
    publish_event = await _event_for(session, publication)
    await request_job_board_unpublication(
        session,
        context=context,
        publication_id=publication.id,
    )
    unpublish_event = await _event_for(
        session,
        publication,
        event_type="job_board.unpublish_requested",
    )
    # The old publish was already attempted once, so recovery must repeat it
    # with the same provider idempotency key to learn its external result.
    publish_event.attempts = 1
    await session.commit()
    provider = FakeJobBoardProvider()
    provider.publish_entered = asyncio.Event()
    provider.publish_release = asyncio.Event()
    factory = async_sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
        autoflush=False,
    )

    async def run_old_publish() -> JobBoardDispatchResult:
        async with factory() as worker_session:
            return await dispatch_job_board_events(
                worker_session,
                worker_id="worker-old-publish",
                providers={provider.provider_key: provider},
                policy=OutboxWorkerPolicy(batch_size=1),
            )

    old_worker = asyncio.create_task(run_old_publish())
    await asyncio.wait_for(provider.publish_entered.wait(), timeout=5)
    async with factory() as newer_session:
        newer_result = await dispatch_job_board_events(
            newer_session,
            worker_id="worker-new-unpublish",
            providers={provider.provider_key: provider},
            policy=OutboxWorkerPolicy(batch_size=1),
        )
    assert newer_result.retried == 1
    provider.publish_release.set()
    old_result = await asyncio.wait_for(old_worker, timeout=5)
    assert old_result.processed == 1

    await session.refresh(publication)
    await session.refresh(publish_event)
    await session.refresh(unpublish_event)
    assert publication.status is JobBoardPublicationStatus.UNPUBLISH_REQUESTED
    assert publication.external_posting_id == "remote-listing-42"
    assert publication.dispatch_locked_by is None
    assert publish_event.status is OutboxEventStatus.PROCESSED
    assert unpublish_event.status is OutboxEventStatus.PENDING
    assert len(provider.publish_commands) == 1
    assert provider.unpublish_commands == []
