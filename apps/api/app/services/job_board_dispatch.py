"""Retry-safe outbox dispatch for external job-board publications."""

import asyncio
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.job_board_publication import JobBoardPublication
from app.db.models.job_posting import JobPosting
from app.db.models.outbox import OutboxEvent
from app.db.transactions import transactional
from app.domains.job_boards.enums import (
    JobBoardPublicationStatus,
)
from app.domains.job_boards.transitions import (
    validate_job_board_publication_transition,
)
from app.domains.job_postings.enums import JobPostingStatus
from app.domains.outbox.enums import OutboxEventStatus
from app.services.audit import record_audit_event
from app.services.job_board_provider import (
    JobBoardProvider,
    JobBoardProviderError,
    PublishJobBoardListingCommand,
    UnpublishJobBoardListingCommand,
)
from app.services.outbox_worker import (
    DEFAULT_OUTBOX_WORKER_POLICY,
    OutboxWorkerPolicy,
    claim_outbox_events,
    dead_letter_outbox_event,
    mark_outbox_event_processed,
    schedule_outbox_event_retry,
)

PUBLISH_EVENT = "job_board.publish_requested"
UNPUBLISH_EVENT = "job_board.unpublish_requested"
JOB_BOARD_EVENT_TYPES = frozenset({PUBLISH_EVENT, UNPUBLISH_EVENT})
_PROVIDER_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_EXTERNAL_ID_MAX_LENGTH = 255
_SYSTEM_SUBJECT_PREFIX = "system:job-board-dispatch"

DispatchOutcome = Literal["processed", "retried", "dead_lettered"]


@dataclass(frozen=True, slots=True)
class JobBoardDispatchResult:
    """Counters from one bounded job-board outbox poll."""

    claimed: int
    processed: int
    retried: int
    dead_lettered: int


@dataclass(frozen=True, slots=True)
class _DispatchRequest:
    """Validated routing fields from an internal outbox event."""

    publication_id: UUID
    generation: int
    provider_key: str
    operation: Literal["publish", "unpublish"]


@dataclass(frozen=True, slots=True)
class _PreparedDispatch:
    """Tenant-scoped immutable snapshot held while the provider is called."""

    event_id: UUID
    tenant_id: UUID
    publication_id: UUID
    generation: int
    lease_token: str
    operation: Literal["publish", "unpublish"]
    provider_key: str
    public_id: UUID
    slug: str
    title: str
    description: str | None
    department: str | None
    location: str | None
    employment_type: str
    expires_at: datetime | None
    external_posting_id: str | None


@dataclass(frozen=True, slots=True)
class _PreparedResult:
    """Either a provider operation or an already handled queue outcome."""

    dispatch: _PreparedDispatch | None
    outcome: DispatchOutcome | None


class JobBoardDispatchLeaseLostError(RuntimeError):
    """Raised when a worker can no longer safely persist its provider result."""


def _now() -> datetime:
    """Return an aware UTC timestamp for leases and synchronization records."""
    return datetime.now(UTC)


def _parse_request(event: OutboxEvent) -> _DispatchRequest | None:
    """Validate payload, aggregate identity, provider, and operation together."""
    if event.aggregate_type != "job_board_publication":
        return None

    payload_value: object = event.payload
    if not isinstance(payload_value, Mapping):
        return None
    payload = cast(Mapping[str, object], payload_value)
    publication_id_value = payload.get("publication_id")
    provider_key = payload.get("provider_key")
    operation = payload.get("operation")
    # `version` is accepted for events created before generation tracking was
    # deployed. New requests use `generation` and retain the same semantics.
    generation = payload.get("generation", payload.get("version"))

    if (
        not isinstance(publication_id_value, str)
        or not isinstance(provider_key, str)
        or not isinstance(operation, str)
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        return None

    try:
        publication_id = UUID(publication_id_value)
    except ValueError:
        return None

    if str(publication_id) != event.aggregate_id:
        return None

    normalized_provider_key = provider_key.strip().lower()
    if _PROVIDER_KEY_PATTERN.fullmatch(normalized_provider_key) is None:
        return None

    expected_event_type = {
        "publish": PUBLISH_EVENT,
        "unpublish": UNPUBLISH_EVENT,
    }.get(operation)
    if expected_event_type != event.event_type:
        return None

    return _DispatchRequest(
        publication_id=publication_id,
        generation=generation,
        provider_key=normalized_provider_key,
        operation=cast(Literal["publish", "unpublish"], operation),
    )


def _system_context(event: OutboxEvent, worker_id: str) -> TenantContext:
    """Build an internal actor context without user or candidate attributes."""
    return TenantContext(
        tenant_id=event.tenant_id,
        subject=f"{_SYSTEM_SUBJECT_PREFIX}:{worker_id}"[:255],
        roles=frozenset(),
        request_id=f"outbox:{event.id}",
    )


async def dispatch_job_board_events(
    session: AsyncSession,
    *,
    worker_id: str,
    providers: Mapping[str, JobBoardProvider],
    policy: OutboxWorkerPolicy = DEFAULT_OUTBOX_WORKER_POLICY,
) -> JobBoardDispatchResult:
    """Claim and dispatch one bounded batch of publish/unpublish events."""
    events = await claim_outbox_events(
        session,
        worker_id=worker_id,
        policy=policy,
        event_types=JOB_BOARD_EVENT_TYPES,
    )

    counts: dict[DispatchOutcome, int] = {
        "processed": 0,
        "retried": 0,
        "dead_lettered": 0,
    }
    for event in events:
        outcome = await _dispatch_event(
            session,
            event=event,
            worker_id=worker_id,
            providers=providers,
            policy=policy,
        )
        counts[outcome] += 1

    return JobBoardDispatchResult(
        claimed=len(events),
        processed=counts["processed"],
        retried=counts["retried"],
        dead_lettered=counts["dead_lettered"],
    )


async def _dispatch_event(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    worker_id: str,
    providers: Mapping[str, JobBoardProvider],
    policy: OutboxWorkerPolicy,
) -> DispatchOutcome:
    """Validate, lease, invoke, and persist one event using stable retry keys."""
    request = _parse_request(event)
    if request is None:
        await dead_letter_outbox_event(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="invalid_job_board_event",
        )
        return "dead_lettered"

    prepared_result = await _prepare_dispatch(
        session,
        event=event,
        request=request,
        worker_id=worker_id,
        policy=policy,
    )
    if prepared_result.outcome is not None:
        return prepared_result.outcome

    prepared = prepared_result.dispatch
    if prepared is None:
        raise RuntimeError("Job-board dispatch preparation returned no outcome.")

    provider = providers.get(prepared.provider_key)
    if provider is None or provider.provider_key != prepared.provider_key:
        return await _handle_provider_failure(
            session,
            event=event,
            prepared=prepared,
            worker_id=worker_id,
            policy=policy,
            retryable=False,
            failure_code="provider_not_configured",
        )

    try:
        provider_timeout = max(
            0.1,
            policy.visibility_timeout.total_seconds() * 0.8,
        )
        async with asyncio.timeout(provider_timeout):
            if prepared.operation == "publish":
                result = await provider.publish(
                    command=PublishJobBoardListingCommand(
                        public_id=prepared.public_id,
                        slug=prepared.slug,
                        title=prepared.title,
                        description=prepared.description,
                        department=prepared.department,
                        location=prepared.location,
                        employment_type=prepared.employment_type,
                        expires_at=prepared.expires_at,
                        external_posting_id=prepared.external_posting_id,
                        idempotency_key=str(prepared.event_id),
                    )
                )
                external_posting_id = _validate_external_posting_id(
                    result.external_posting_id
                )
            else:
                if prepared.external_posting_id is None:
                    raise RuntimeError("Unpublish requires a remote posting reference.")
                await provider.unpublish(
                    command=UnpublishJobBoardListingCommand(
                        public_id=prepared.public_id,
                        external_posting_id=prepared.external_posting_id,
                        idempotency_key=str(prepared.event_id),
                    )
                )
                external_posting_id = None
    except TimeoutError:
        return await _handle_provider_failure(
            session,
            event=event,
            prepared=prepared,
            worker_id=worker_id,
            policy=policy,
            retryable=True,
            failure_code="provider_timeout",
        )
    except JobBoardProviderError as error:
        return await _handle_provider_failure(
            session,
            event=event,
            prepared=prepared,
            worker_id=worker_id,
            policy=policy,
            retryable=error.retryable,
            failure_code=(
                "provider_retryable_error"
                if error.retryable
                else "provider_terminal_error"
            ),
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # Adapter exception text is deliberately neither logged nor persisted.
        return await _handle_provider_failure(
            session,
            event=event,
            prepared=prepared,
            worker_id=worker_id,
            policy=policy,
            retryable=True,
            failure_code="provider_unexpected_error",
        )

    try:
        await _persist_provider_success(
            session,
            prepared=prepared,
            worker_id=worker_id,
            external_posting_id=external_posting_id,
        )
    except JobBoardDispatchLeaseLostError:
        # The current lease owner will retry the same event with its stable
        # provider idempotency key; never let an expired owner overwrite state.
        return "retried"
    except Exception:  # pylint: disable=broad-exception-caught
        await _release_dispatch_lease(
            session,
            prepared=prepared,
        )
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code="provider_result_persistence_error",
            policy=policy,
        )
        return "retried"

    try:
        await mark_outbox_event_processed(
            session,
            event_id=event.id,
            worker_id=worker_id,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        # If the acknowledgement failed after the result transaction committed,
        # redelivery observes the persisted state and safely acknowledges it.
        return "retried"

    return "processed"


async def _prepare_dispatch(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    request: _DispatchRequest,
    worker_id: str,
    policy: OutboxWorkerPolicy,
) -> _PreparedResult:
    """Load tenant-owned snapshot and reserve a publication-scoped lease."""
    now = _now()
    lease_token = str(uuid4())
    context = _system_context(event, worker_id)

    async with transactional(session):
        publication = await session.scalar(
            select(JobBoardPublication)
            .where(
                JobBoardPublication.id == request.publication_id,
                JobBoardPublication.tenant_id == event.tenant_id,
            )
            .with_for_update()
        )
        if publication is None:
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_publication_not_found",
            )
            return _PreparedResult(None, "dead_lettered")

        if publication.provider_key != request.provider_key:
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_provider_mismatch",
            )
            return _PreparedResult(None, "dead_lettered")

        if request.generation > publication.desired_generation:
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_future_generation",
            )
            return _PreparedResult(None, "dead_lettered")

        stale = request.generation < publication.desired_generation
        if stale and publication.last_synced_generation > request.generation:
            # A later desired state already reached the remote provider. Replaying
            # this older event could undo that newer state (for example, a stale
            # unpublish arriving after a successful republish).
            await mark_outbox_event_processed(
                session,
                event_id=event.id,
                worker_id=worker_id,
            )
            return _PreparedResult(None, "processed")
        if stale and event.attempts <= 1:
            await mark_outbox_event_processed(
                session,
                event_id=event.id,
                worker_id=worker_id,
            )
            return _PreparedResult(None, "processed")

        expected_status = (
            JobBoardPublicationStatus.PUBLISH_REQUESTED
            if request.operation == "publish"
            else JobBoardPublicationStatus.UNPUBLISH_REQUESTED
        )
        already_complete = (
            request.operation == "publish"
            and publication.status is JobBoardPublicationStatus.PUBLISHED
            and publication.external_posting_id is not None
        ) or (
            request.operation == "unpublish"
            and publication.status is JobBoardPublicationStatus.UNPUBLISHED
        )
        if not stale and already_complete:
            await mark_outbox_event_processed(
                session,
                event_id=event.id,
                worker_id=worker_id,
            )
            return _PreparedResult(None, "processed")

        if not stale and publication.status is not expected_status:
            if publication.status is JobBoardPublicationStatus.FAILED:
                await mark_outbox_event_processed(
                    session,
                    event_id=event.id,
                    worker_id=worker_id,
                )
                return _PreparedResult(None, "processed")
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_publication_not_dispatchable",
            )
            return _PreparedResult(None, "dead_lettered")

        if (
            publication.dispatch_locked_until is not None
            and publication.dispatch_locked_until > now
        ):
            await schedule_outbox_event_retry(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_publication_busy",
                policy=policy,
            )
            return _PreparedResult(None, "retried")

        publication.dispatch_locked_by = lease_token
        publication.dispatch_locked_until = now + policy.visibility_timeout
        await session.flush()

        posting = await session.scalar(
            select(JobPosting).where(
                JobPosting.id == publication.job_posting_id,
                JobPosting.tenant_id == event.tenant_id,
            )
        )
        if posting is None:
            publication.dispatch_locked_by = None
            publication.dispatch_locked_until = None
            await session.flush()
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_board_posting_not_found",
            )
            return _PreparedResult(None, "dead_lettered")

        if (
            request.operation == "publish"
            and not stale
            and posting.status is not JobPostingStatus.PUBLISHED
        ):
            publication.dispatch_locked_by = None
            publication.dispatch_locked_until = None
            validate_job_board_publication_transition(
                publication.status,
                JobBoardPublicationStatus.FAILED,
            )
            publication.status = JobBoardPublicationStatus.FAILED
            publication.last_error_code = "job_posting_not_published"
            await session.flush()
            _record_dispatch_audit(
                session,
                context=context,
                publication=publication,
                operation=request.operation,
                action="job_board.publication.dispatch_failed",
                failure_code="job_posting_not_published",
            )
            await dead_letter_outbox_event(
                session,
                event_id=event.id,
                worker_id=worker_id,
                failure_code="job_posting_not_published",
            )
            return _PreparedResult(None, "dead_lettered")

        if request.operation == "unpublish" and publication.external_posting_id is None:
            pending_publish = await session.scalar(
                select(OutboxEvent.id)
                .where(
                    OutboxEvent.tenant_id == event.tenant_id,
                    OutboxEvent.aggregate_type == "job_board_publication",
                    OutboxEvent.aggregate_id == str(publication.id),
                    OutboxEvent.event_type == PUBLISH_EVENT,
                    OutboxEvent.status.in_(
                        [OutboxEventStatus.PENDING, OutboxEventStatus.PROCESSING]
                    ),
                    OutboxEvent.id != event.id,
                )
                .limit(1)
            )
            if pending_publish is not None:
                publication.dispatch_locked_by = None
                publication.dispatch_locked_until = None
                await session.flush()
                await schedule_outbox_event_retry(
                    session,
                    event_id=event.id,
                    worker_id=worker_id,
                    failure_code="job_board_publish_in_progress",
                    policy=policy,
                )
                return _PreparedResult(None, "retried")

            # There is no remote reference to remove. In particular, do not
            # call a provider and do not report an unneeded delete as an error.
            publication.dispatch_locked_by = None
            publication.dispatch_locked_until = None
            if not stale:
                validate_job_board_publication_transition(
                    publication.status,
                    JobBoardPublicationStatus.UNPUBLISHED,
                )
                publication.status = JobBoardPublicationStatus.UNPUBLISHED
                publication.last_synced_at = now
                publication.last_synced_generation = max(
                    publication.last_synced_generation,
                    request.generation,
                )
                publication.last_error_code = None
                _record_dispatch_audit(
                    session,
                    context=context,
                    publication=publication,
                    operation=request.operation,
                    action="job_board.publication.synchronized",
                )
            await session.flush()
            await mark_outbox_event_processed(
                session,
                event_id=event.id,
                worker_id=worker_id,
            )
            return _PreparedResult(None, "processed")

        return _PreparedResult(
            _PreparedDispatch(
                event_id=event.id,
                tenant_id=event.tenant_id,
                publication_id=publication.id,
                generation=request.generation,
                lease_token=lease_token,
                operation=request.operation,
                provider_key=publication.provider_key,
                public_id=posting.public_id,
                slug=posting.slug,
                title=posting.title,
                description=posting.description,
                department=posting.department,
                location=posting.location,
                employment_type=posting.employment_type.value,
                expires_at=posting.expires_at,
                external_posting_id=publication.external_posting_id,
            ),
            None,
        )


def _validate_external_posting_id(value: str) -> str:
    """Reject empty, oversized, or control-character provider references."""
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > _EXTERNAL_ID_MAX_LENGTH
        or any(ord(character) < 32 or ord(character) == 127 for character in normalized)
    ):
        raise JobBoardProviderError(
            "invalid_external_posting_id",
            retryable=False,
        )
    return normalized


def _record_dispatch_audit(
    session: AsyncSession,
    *,
    context: TenantContext,
    publication: JobBoardPublication,
    operation: str,
    action: str,
    failure_code: str | None = None,
) -> None:
    """Record only identifiers, operation type, generation, and safe codes."""
    details: dict[str, str | int] = {
        "provider_key": publication.provider_key,
        "operation": operation,
        "generation": publication.desired_generation,
    }
    if failure_code is not None:
        details["failure_code"] = failure_code
    record_audit_event(
        session,
        context=context,
        action=action,
        entity_type="job_board_publication",
        entity_id=str(publication.id),
        details=details,
    )


async def _persist_provider_success(
    session: AsyncSession,
    *,
    prepared: _PreparedDispatch,
    worker_id: str,
    external_posting_id: str | None,
) -> None:
    """Persist provider outcome without overwriting a newer desired state."""
    event_context = TenantContext(
        tenant_id=prepared.tenant_id,
        subject=f"{_SYSTEM_SUBJECT_PREFIX}:{worker_id}"[:255],
        roles=frozenset(),
        request_id=f"outbox:{prepared.event_id}",
    )
    async with transactional(session):
        publication = await session.scalar(
            select(JobBoardPublication)
            .where(
                JobBoardPublication.id == prepared.publication_id,
                JobBoardPublication.tenant_id == prepared.tenant_id,
            )
            .with_for_update()
        )
        if (
            publication is None
            or publication.dispatch_locked_by != prepared.lease_token
        ):
            raise JobBoardDispatchLeaseLostError(
                "Publication dispatch lease is no longer owned."
            )

        if prepared.operation == "publish":
            if external_posting_id is None:
                raise RuntimeError("Publish success requires an external identifier.")
            publication.external_posting_id = external_posting_id
        publication.last_synced_generation = max(
            publication.last_synced_generation,
            prepared.generation,
        )

        if publication.desired_generation == prepared.generation:
            target_status = (
                JobBoardPublicationStatus.PUBLISHED
                if prepared.operation == "publish"
                else JobBoardPublicationStatus.UNPUBLISHED
            )
            expected_status = (
                JobBoardPublicationStatus.PUBLISH_REQUESTED
                if prepared.operation == "publish"
                else JobBoardPublicationStatus.UNPUBLISH_REQUESTED
            )
            if publication.status is expected_status:
                validate_job_board_publication_transition(
                    publication.status,
                    target_status,
                )
                publication.status = target_status
                publication.last_error_code = None

        publication.last_synced_at = _now()
        publication.dispatch_locked_by = None
        publication.dispatch_locked_until = None
        _record_dispatch_audit(
            session,
            context=event_context,
            publication=publication,
            operation=prepared.operation,
            action="job_board.publication.synchronized",
        )
        await session.flush()


async def _release_dispatch_lease(
    session: AsyncSession,
    *,
    prepared: _PreparedDispatch,
    failure_code: str | None = None,
    terminal: bool = False,
) -> bool:
    """Release an owned lease and optionally record a classified failure."""
    context = TenantContext(
        tenant_id=prepared.tenant_id,
        subject=f"{_SYSTEM_SUBJECT_PREFIX}:recovery"[:255],
        roles=frozenset(),
        request_id=f"outbox:{prepared.event_id}",
    )
    async with transactional(session):
        publication = await session.scalar(
            select(JobBoardPublication)
            .where(
                JobBoardPublication.id == prepared.publication_id,
                JobBoardPublication.tenant_id == prepared.tenant_id,
            )
            .with_for_update()
        )
        if (
            publication is None
            or publication.dispatch_locked_by != prepared.lease_token
        ):
            return False

        if failure_code is not None and (
            publication.desired_generation == prepared.generation
        ):
            publication.last_error_code = failure_code
            if terminal:
                requested_status = (
                    JobBoardPublicationStatus.PUBLISH_REQUESTED
                    if prepared.operation == "publish"
                    else JobBoardPublicationStatus.UNPUBLISH_REQUESTED
                )
                if publication.status is requested_status:
                    validate_job_board_publication_transition(
                        publication.status,
                        JobBoardPublicationStatus.FAILED,
                    )
                    publication.status = JobBoardPublicationStatus.FAILED
                _record_dispatch_audit(
                    session,
                    context=context,
                    publication=publication,
                    operation=prepared.operation,
                    action="job_board.publication.dispatch_failed",
                    failure_code=failure_code,
                )

        publication.dispatch_locked_by = None
        publication.dispatch_locked_until = None
        await session.flush()

    return True


async def _handle_provider_failure(
    session: AsyncSession,
    *,
    event: OutboxEvent,
    prepared: _PreparedDispatch,
    worker_id: str,
    policy: OutboxWorkerPolicy,
    retryable: bool,
    failure_code: str,
) -> DispatchOutcome:
    """Persist a safe classification, release the publication lease, and retry."""
    released = await _release_dispatch_lease(
        session,
        prepared=prepared,
        failure_code=failure_code,
        terminal=not retryable,
    )
    if not released:
        return "retried"

    if retryable:
        await schedule_outbox_event_retry(
            session,
            event_id=event.id,
            worker_id=worker_id,
            failure_code=failure_code,
            policy=policy,
        )
        return "retried"

    await dead_letter_outbox_event(
        session,
        event_id=event.id,
        worker_id=worker_id,
        failure_code=failure_code,
    )
    return "dead_lettered"
