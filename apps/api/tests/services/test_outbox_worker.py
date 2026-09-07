"""PostgreSQL integration tests for transactional outbox worker behavior."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.outbox.enums import OutboxEventStatus
from app.services.outbox_errors import OutboxEventLeaseLostError
from app.services.outbox_worker import (
    OutboxWorkerPolicy,
    claim_outbox_events,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)


@pytest_asyncio.fixture(name="outbox_session_factory")
async def outbox_session_factory_fixture(
    database_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide independent sessions needed to test concurrent worker behavior."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    yield session_factory

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )


async def _seed_events(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    count: int,
    status: OutboxEventStatus = OutboxEventStatus.PENDING,
    attempts: int = 0,
    locked_at: datetime | None = None,
    locked_by: str | None = None,
) -> tuple[UUID, list[UUID]]:
    """Create one tenant and one or more outbox events for a worker test."""
    tenant_id = uuid4()
    event_ids: list[UUID] = []
    now = datetime.now(UTC)

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Outbox Tenant {tenant_id.hex[:12]}",
                slug=f"outbox-{tenant_id.hex[:12]}",
            )
        )

        for position in range(count):
            event = OutboxEvent(
                tenant_id=tenant_id,
                event_type="candidate_document.scan_requested",
                aggregate_type="candidate_document",
                aggregate_id=str(uuid4()),
                deduplication_key=f"scan-request-{tenant_id}-{position}",
                payload={"document_id": str(uuid4())},
                status=status,
                attempts=attempts,
                locked_at=locked_at,
                locked_by=locked_by,
                    next_attempt_at=now - timedelta(seconds=1),
            )
            session.add(event)
            await session.flush()
            event_ids.append(event.id)

    return tenant_id, event_ids


async def _get_event(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
) -> OutboxEvent:
    """Load one outbox event after a worker operation commits."""
    async with session_factory() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None
        return event


@pytest.mark.asyncio
async def test_skip_locked_claim_allows_another_worker_to_progress(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Skip a row locked by one worker instead of blocking a second worker."""
    _, event_ids = await _seed_events(outbox_session_factory, count=2)
    locked_event_id, available_event_id = event_ids
    policy = OutboxWorkerPolicy(batch_size=1)

    async with outbox_session_factory() as locking_session:
        async with locking_session.begin():
            locked_event = await locking_session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.id == locked_event_id)
                .with_for_update()
            )
            assert locked_event is not None

            async with outbox_session_factory() as worker_session:
                claimed = await claim_outbox_events(
                    worker_session,
                    worker_id="worker-two",
                    policy=policy,
                )

            assert [event.id for event in claimed] == [available_event_id]


@pytest.mark.asyncio
async def test_recovers_stale_lease_and_reclaims_event(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Return stale in-progress work to the pending queue before claiming it."""
    stale_at = datetime.now(UTC) - timedelta(minutes=10)
    _, event_ids = await _seed_events(
        outbox_session_factory,
        count=1,
        status=OutboxEventStatus.PROCESSING,
        attempts=1,
        locked_at=stale_at,
        locked_by="crashed-worker",
    )
    policy = OutboxWorkerPolicy(
        batch_size=1,
        max_attempts=3,
        visibility_timeout=timedelta(minutes=1),
    )

    async with outbox_session_factory() as session:
        claimed = await claim_outbox_events(
            session,
            worker_id="recovery-worker",
            policy=policy,
        )

    assert [event.id for event in claimed] == event_ids

    event = await _get_event(outbox_session_factory, event_ids[0])
    assert event.status is OutboxEventStatus.PROCESSING
    assert event.locked_by == "recovery-worker"
    assert event.attempts == 2
    assert event.last_error == "lease_expired"


@pytest.mark.asyncio
async def test_retries_with_capped_exponential_backoff(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Increase retry delay after each failed processing attempt."""
    _, event_ids = await _seed_events(outbox_session_factory, count=1)
    event_id = event_ids[0]
    policy = OutboxWorkerPolicy(
        batch_size=1,
        max_attempts=4,
        base_retry_delay=timedelta(seconds=10),
        maximum_retry_delay=timedelta(seconds=60),
    )

    async with outbox_session_factory() as session:
        first_claim = await claim_outbox_events(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        first_start = datetime.now(UTC)
        first_retry = await schedule_outbox_event_retry(
            session,
            event_id=first_claim[0].id,
            worker_id="worker-one",
            failure_code="scanner_unavailable",
            policy=policy,
        )
        first_end = datetime.now(UTC)

    assert first_retry.status is OutboxEventStatus.PENDING
    assert first_retry.attempts == 1
    assert first_start + timedelta(seconds=10) <= first_retry.next_attempt_at
    assert first_retry.next_attempt_at <= first_end + timedelta(seconds=10)

    async with outbox_session_factory.begin() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event is not None
        event.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

    async with outbox_session_factory() as session:
        second_claim = await claim_outbox_events(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        second_start = datetime.now(UTC)
        second_retry = await schedule_outbox_event_retry(
            session,
            event_id=second_claim[0].id,
            worker_id="worker-one",
            failure_code="scanner_unavailable",
            policy=policy,
        )
        second_end = datetime.now(UTC)

    assert second_retry.status is OutboxEventStatus.PENDING
    assert second_retry.attempts == 2
    assert second_start + timedelta(seconds=20) <= second_retry.next_attempt_at
    assert second_retry.next_attempt_at <= second_end + timedelta(seconds=20)


@pytest.mark.asyncio
async def test_prevents_a_worker_from_completing_another_workers_lease(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Require the worker that claimed an event to complete it."""
    _, event_ids = await _seed_events(outbox_session_factory, count=1)

    async with outbox_session_factory() as session:
        claimed = await claim_outbox_events(
            session,
            worker_id="worker-one",
        )

        with pytest.raises(OutboxEventLeaseLostError):
            await mark_outbox_event_processed(
                session,
                event_id=claimed[0].id,
                worker_id="worker-two",
            )

        processed = await mark_outbox_event_processed(
            session,
            event_id=event_ids[0],
            worker_id="worker-one",
        )

    assert processed.id == event_ids[0]
    assert processed.status is OutboxEventStatus.PROCESSED
    assert processed.processed_at is not None
    assert processed.locked_at is None
    assert processed.locked_by is None


@pytest.mark.asyncio
async def test_dead_letters_event_after_maximum_attempts(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stop retrying terminal failures after the configured attempt limit."""
    _, event_ids = await _seed_events(outbox_session_factory, count=1)
    policy = OutboxWorkerPolicy(
        batch_size=1,
        max_attempts=1,
    )

    async with outbox_session_factory() as session:
        claimed = await claim_outbox_events(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        dead_lettered = await schedule_outbox_event_retry(
            session,
            event_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="scanner_rejected_request",
            policy=policy,
        )

    assert dead_lettered.id == event_ids[0]
    assert dead_lettered.status is OutboxEventStatus.DEAD_LETTERED
    assert dead_lettered.attempts == 1
    assert dead_lettered.dead_lettered_at is not None
    assert dead_lettered.last_error == "scanner_rejected_request"


@pytest.mark.asyncio
async def test_dead_letters_stale_event_that_already_exhausted_attempts(
    outbox_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Do not revive stale events once they have exhausted their retry budget."""
    stale_at = datetime.now(UTC) - timedelta(minutes=10)
    _, event_ids = await _seed_events(
        outbox_session_factory,
        count=1,
        status=OutboxEventStatus.PROCESSING,
        attempts=2,
        locked_at=stale_at,
        locked_by="crashed-worker",
    )
    policy = OutboxWorkerPolicy(
        batch_size=1,
        max_attempts=2,
        visibility_timeout=timedelta(minutes=1),
    )

    async with outbox_session_factory() as session:
        claimed = await claim_outbox_events(
            session,
            worker_id="recovery-worker",
            policy=policy,
        )

    event = await _get_event(outbox_session_factory, event_ids[0])

    assert not claimed
    assert event.status is OutboxEventStatus.DEAD_LETTERED
    assert event.dead_lettered_at is not None
    assert event.last_error == "lease_expired"
