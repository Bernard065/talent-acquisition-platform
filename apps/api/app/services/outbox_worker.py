"""Database claim, retry, and dead-letter operations for outbox workers."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.outbox import OutboxEvent
from app.db.transactions import transactional
from app.domains.outbox.enums import OutboxEventStatus
from app.services.outbox_errors import (
    OutboxEventLeaseLostError,
    OutboxEventNotFoundError,
)

_FAILURE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True, slots=True)
class OutboxWorkerPolicy:
    """Retry and lease settings for a durable outbox worker."""

    batch_size: int = 10
    max_attempts: int = 8
    visibility_timeout: timedelta = timedelta(minutes=5)
    base_retry_delay: timedelta = timedelta(seconds=30)
    maximum_retry_delay: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 100:
            raise ValueError("Outbox worker batch size must be between 1 and 100.")

        if not 1 <= self.max_attempts <= 100:
            raise ValueError("Outbox worker max attempts must be between 1 and 100.")

        if self.visibility_timeout <= timedelta():
            raise ValueError("Outbox worker visibility timeout must be positive.")

        if self.base_retry_delay <= timedelta():
            raise ValueError("Outbox worker base retry delay must be positive.")

        if self.maximum_retry_delay < self.base_retry_delay:
            raise ValueError(
                "Outbox worker maximum retry delay must not be smaller than base delay."
            )


DEFAULT_OUTBOX_WORKER_POLICY = OutboxWorkerPolicy()


def _now() -> datetime:
    """Return a timezone-aware current timestamp."""
    return datetime.now(UTC)


def _validate_worker_id(worker_id: str) -> str:
    """Validate and normalize the worker identifier stored in a lease."""
    normalized = worker_id.strip()

    if not normalized:
        raise ValueError("Outbox worker ID is required.")

    if len(normalized) > 255:
        raise ValueError("Outbox worker ID must not exceed 255 characters.")

    return normalized


def _validate_failure_code(failure_code: str) -> str:
    """Accept only safe classification codes, never raw exception messages."""
    normalized = failure_code.strip().lower()

    if not _FAILURE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Outbox failure code must contain only lowercase letters, digits, "
            "periods, underscores, and hyphens."
        )

    return normalized


def _retry_delay(
    *,
    attempts: int,
    policy: OutboxWorkerPolicy,
) -> timedelta:
    """Calculate capped exponential retry delay based on completed claims."""
    multiplier = 2 ** max(attempts - 1, 0)
    delay = cast(timedelta, policy.base_retry_delay * multiplier)

    if delay > policy.maximum_retry_delay:
        return policy.maximum_retry_delay

    return delay


async def claim_outbox_events(
    session: AsyncSession,
    *,
    worker_id: str,
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
    event_types: frozenset[str] | None = None,
) -> list[OutboxEvent]:
    """
    Recover stale leases and atomically claim ready events.

    `FOR UPDATE SKIP LOCKED` lets multiple worker instances process separate
    events concurrently without waiting on each other.
    """
    normalized_worker_id = _validate_worker_id(worker_id)
    now = _now()
    stale_before = now - policy.visibility_timeout

    async with transactional(session):
        # Stale leases that have already exhausted their allowed attempts are
        # terminal. A human or future replay workflow can inspect dead letters.
        await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxEventStatus.PROCESSING,
                OutboxEvent.locked_at.is_not(None),
                OutboxEvent.locked_at < stale_before,
                OutboxEvent.attempts >= policy.max_attempts,
            )
            .values(
                status=OutboxEventStatus.DEAD_LETTERED,
                locked_at=None,
                locked_by=None,
                dead_lettered_at=now,
                last_error="lease_expired",
            )
        )

        # Recover remaining stale leases so another worker can retry them.
        await session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == OutboxEventStatus.PROCESSING,
                OutboxEvent.locked_at.is_not(None),
                OutboxEvent.locked_at < stale_before,
                OutboxEvent.attempts < policy.max_attempts,
            )
            .values(
                status=OutboxEventStatus.PENDING,
                locked_at=None,
                locked_by=None,
                next_attempt_at=now,
                last_error="lease_expired",
            )
        )

        if event_types is not None and not event_types:
            raise ValueError("Outbox event types must not be empty when supplied.")

        statement = select(OutboxEvent).where(
            OutboxEvent.status == OutboxEventStatus.PENDING,
            OutboxEvent.next_attempt_at <= now,
        )

        if event_types is not None:
            statement = statement.where(OutboxEvent.event_type.in_(event_types))

        events = list(
            await session.scalars(
                statement.order_by(
                    OutboxEvent.next_attempt_at,
                    OutboxEvent.created_at,
                    OutboxEvent.id,
                )
                .with_for_update(skip_locked=True)
                .limit(policy.batch_size)
            )
        )

        for event in events:
            event.status = OutboxEventStatus.PROCESSING
            event.locked_at = now
            event.locked_by = normalized_worker_id
            event.attempts += 1

        await session.flush()

    return events


async def mark_outbox_event_processed(
    session: AsyncSession,
    *,
    event_id: UUID,
    worker_id: str,
) -> OutboxEvent:
    """Mark a leased event as successfully processed by its owning worker."""
    normalized_worker_id = _validate_worker_id(worker_id)

    async with transactional(session):
        event = await _get_leased_event(
            session,
            event_id=event_id,
            worker_id=normalized_worker_id,
        )

        event.status = OutboxEventStatus.PROCESSED
        event.processed_at = _now()
        event.locked_at = None
        event.locked_by = None
        event.last_error = None

        await session.flush()

    return event


async def schedule_outbox_event_retry(
    session: AsyncSession,
    *,
    event_id: UUID,
    worker_id: str,
    failure_code: str,
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> OutboxEvent:
    """
    Release a failed lease for retry or move it to the dead-letter queue.

    `failure_code` is deliberately a short classification, never a provider
    exception string that could contain implementation or sensitive details.
    """
    normalized_worker_id = _validate_worker_id(worker_id)
    normalized_failure_code = _validate_failure_code(failure_code)
    now = _now()

    async with transactional(session):
        event = await _get_leased_event(
            session,
            event_id=event_id,
            worker_id=normalized_worker_id,
        )
        event.locked_at = None
        event.locked_by = None
        event.last_error = normalized_failure_code

        if event.attempts >= policy.max_attempts:
            event.status = OutboxEventStatus.DEAD_LETTERED
            event.dead_lettered_at = now
        else:
            event.status = OutboxEventStatus.PENDING
            event.next_attempt_at = now + _retry_delay(
                attempts=event.attempts,
                policy=policy,
            )

        await session.flush()

    return event


async def dead_letter_outbox_event(
    session: AsyncSession,
    *,
    event_id: UUID,
    worker_id: str,
    failure_code: str,
) -> OutboxEvent:
    """Terminally fail a leased event that cannot ever be processed."""
    normalized_worker_id = _validate_worker_id(worker_id)
    normalized_failure_code = _validate_failure_code(failure_code)

    async with transactional(session):
        event = await _get_leased_event(
            session,
            event_id=event_id,
            worker_id=normalized_worker_id,
        )

        event.status = OutboxEventStatus.DEAD_LETTERED
        event.locked_at = None
        event.locked_by = None
        event.dead_lettered_at = _now()
        event.last_error = normalized_failure_code

        await session.flush()

    return event


async def _get_leased_event(
    session: AsyncSession,
    *,
    event_id: UUID,
    worker_id: str,
) -> OutboxEvent:
    """Load one event only when the current worker still owns its lease."""
    event = await session.scalar(
        select(OutboxEvent)
        .where(OutboxEvent.id == event_id)
        .with_for_update()
    )
    if event is None:
        raise OutboxEventNotFoundError("Outbox event was not found.")

    if (
        event.status is not OutboxEventStatus.PROCESSING
        or event.locked_by != worker_id
    ):
        raise OutboxEventLeaseLostError(
            "Outbox event is no longer leased by this worker."
        )

    return event
