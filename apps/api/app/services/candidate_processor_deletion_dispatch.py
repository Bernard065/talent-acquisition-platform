"""Lease, retry, and dispatch candidate processor deletion requests."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.calendar import CalendarConnection, InterviewCalendarSync
from app.db.models.candidate_processor import (
    CandidateProcessorDeletionRequest,
    CandidateProcessorDisclosure,
)
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.transactions import transactional
from app.domains.candidates.processor_data import CandidateProcessorDeletionStatus
from app.services.audit import record_audit_event
from app.services.candidate_processor_errors import (
    CandidateProcessorDeletionLeaseLostError,
)
from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionCommand,
    CandidateProcessorDeletionProvider,
    CandidateProcessorProviderError,
)

_FAILURE_CODE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True, slots=True)
class CandidateProcessorDeletionPolicy:
    """Bounded worker lease and exponential retry configuration."""

    batch_size: int = 25
    max_attempts: int = 8
    lease_timeout: timedelta = timedelta(minutes=5)
    base_retry_delay: timedelta = timedelta(seconds=30)
    maximum_retry_delay: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 100:
            raise ValueError("Processor deletion batch size must be between 1 and 100.")
        if not 1 <= self.max_attempts <= 100:
            raise ValueError("Processor deletion max attempts must be between 1 and 100.")
        if self.lease_timeout <= timedelta():
            raise ValueError("Processor deletion lease timeout must be positive.")
        if self.base_retry_delay <= timedelta():
            raise ValueError("Processor deletion retry delay must be positive.")
        if self.maximum_retry_delay < self.base_retry_delay:
            raise ValueError("Maximum retry delay must not be below base retry delay.")


DEFAULT_CANDIDATE_PROCESSOR_DELETION_POLICY = CandidateProcessorDeletionPolicy()


@dataclass(frozen=True, slots=True)
class CandidateProcessorDeletionDispatchResult:
    """Counts from one bounded processor-deletion worker poll."""

    claimed: int
    completed: int
    retried: int
    exceptions: int
    lease_lost: int


@dataclass(frozen=True, slots=True)
class _Claim:
    request_id: UUID
    tenant_id: UUID
    lease_version: int


class _PreparationError(RuntimeError):
    """Safe failure code for inconsistent or incomplete local references."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _worker_context(*, tenant_id: UUID, worker_id: str, request_id: UUID) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=f"system:processor-deletion:{worker_id}",
        roles=frozenset({Role.PEOPLE_OPERATIONS}),
        request_id=f"processor-deletion:{request_id}",
    )


def _retry_delay(*, attempts: int, policy: CandidateProcessorDeletionPolicy) -> timedelta:
    delay = cast(timedelta, policy.base_retry_delay * (2 ** max(attempts - 1, 0)))
    return min(delay, policy.maximum_retry_delay)


def _failure_code(value: str) -> str:
    normalized = value.strip().lower()
    return normalized if _FAILURE_CODE_PATTERN.fullmatch(normalized) else "provider_error"


async def _claim_requests(
    session: AsyncSession,
    *,
    worker_id: str,
    policy: CandidateProcessorDeletionPolicy,
) -> list[_Claim]:
    """Recover expired leases and claim a bounded batch using SKIP LOCKED."""
    normalized_worker_id = worker_id.strip()
    if not normalized_worker_id or len(normalized_worker_id) > 255:
        raise ValueError("Processor deletion worker ID is invalid.")

    now = _now()
    stale_before = now - policy.lease_timeout
    async with transactional(session):
        stale = list(
            await session.scalars(
                select(CandidateProcessorDeletionRequest)
                .where(
                    CandidateProcessorDeletionRequest.status
                    == CandidateProcessorDeletionStatus.PROCESSING.value,
                    CandidateProcessorDeletionRequest.locked_at < stale_before,
                )
                .order_by(
                    CandidateProcessorDeletionRequest.locked_at,
                    CandidateProcessorDeletionRequest.created_at,
                )
                .with_for_update(skip_locked=True)
                .limit(policy.batch_size)
            )
        )
        for request in stale:
            request.locked_at = None
            request.locked_by = None
            request.last_failure_code = "lease_expired"
            context = _worker_context(
                tenant_id=request.tenant_id,
                worker_id=normalized_worker_id,
                request_id=request.id,
            )
            if request.attempt_count >= policy.max_attempts:
                request.status = CandidateProcessorDeletionStatus.EXCEPTION.value
                request.resolution_code = "retry_exhausted"
                request.status_changed_at = now
                request.status_changed_by_subject = context.subject
                record_audit_event(
                    session,
                    context=context,
                    action="candidate.processor_deletion_exception_recorded",
                    entity_type="candidate_processor_deletion_request",
                    entity_id=str(request.id),
                    details={
                        "status": CandidateProcessorDeletionStatus.EXCEPTION.value,
                        "resolution_code": "retry_exhausted",
                        "failure_code": "lease_expired",
                        "attempt_count": request.attempt_count,
                    },
                )
            else:
                request.status = CandidateProcessorDeletionStatus.PENDING.value
                request.next_attempt_at = now

        await session.flush()

        ready = list(
            await session.scalars(
                select(CandidateProcessorDeletionRequest)
                .where(
                    CandidateProcessorDeletionRequest.status
                    == CandidateProcessorDeletionStatus.PENDING.value,
                    CandidateProcessorDeletionRequest.next_attempt_at <= now,
                )
                .order_by(
                    CandidateProcessorDeletionRequest.next_attempt_at,
                    CandidateProcessorDeletionRequest.created_at,
                    CandidateProcessorDeletionRequest.id,
                )
                .with_for_update(skip_locked=True)
                .limit(policy.batch_size)
            )
        )
        for request in ready:
            request.status = CandidateProcessorDeletionStatus.PROCESSING.value
            request.locked_at = now
            request.locked_by = normalized_worker_id
            request.attempt_count += 1
            context = _worker_context(
                tenant_id=request.tenant_id,
                worker_id=normalized_worker_id,
                request_id=request.id,
            )
            record_audit_event(
                session,
                context=context,
                action="candidate.processor_deletion_dispatch_started",
                entity_type="candidate_processor_deletion_request",
                entity_id=str(request.id),
                details={
                    "status": CandidateProcessorDeletionStatus.PROCESSING.value,
                    "attempt_count": request.attempt_count,
                },
            )
        await session.flush()
        return [
            _Claim(
                request_id=request.id,
                tenant_id=request.tenant_id,
                lease_version=request.version,
            )
            for request in ready
        ]


async def _build_command(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
) -> CandidateProcessorDeletionCommand:
    """Load only opaque provider metadata and required credential references."""
    request = await session.scalar(
        select(CandidateProcessorDeletionRequest)
        .where(
            CandidateProcessorDeletionRequest.id == claim.request_id,
            CandidateProcessorDeletionRequest.tenant_id == claim.tenant_id,
            CandidateProcessorDeletionRequest.status
            == CandidateProcessorDeletionStatus.PROCESSING.value,
            CandidateProcessorDeletionRequest.locked_by == worker_id,
            CandidateProcessorDeletionRequest.version == claim.lease_version,
        )
        .with_for_update()
    )
    if request is None:
        raise CandidateProcessorDeletionLeaseLostError(
            "Processor deletion request lease is no longer owned by this worker."
        )
    disclosure = await session.scalar(
        select(CandidateProcessorDisclosure).where(
            CandidateProcessorDisclosure.id == request.disclosure_id,
            CandidateProcessorDisclosure.tenant_id == request.tenant_id,
        )
    )
    if disclosure is None or disclosure.external_record_reference is None:
        raise _PreparationError("processor_reference_unavailable")

    credential_reference: str | None = None
    calendar_connection_id: UUID | None = None
    interview_session_id: UUID | None = None
    external_calendar_id: str | None = None
    if disclosure.processor_code == "calendar.google":
        if disclosure.source_type != "calendar_sync":
            raise _PreparationError("processor_source_mismatch")
        sync = await session.scalar(
            select(InterviewCalendarSync).where(
                InterviewCalendarSync.id == disclosure.source_id,
                InterviewCalendarSync.tenant_id == request.tenant_id,
            )
        )
        if sync is None:
            raise _PreparationError("processor_source_unavailable")
        connection = await session.scalar(
            select(CalendarConnection).where(
                CalendarConnection.id == sync.calendar_connection_id,
                CalendarConnection.tenant_id == request.tenant_id,
            )
        )
        if connection is None or connection.provider.value != "google":
            raise _PreparationError("processor_connection_unavailable")
        credential_reference = connection.credential_reference
        calendar_connection_id = connection.id
        interview_session_id = sync.interview_session_id
        external_calendar_id = connection.external_calendar_id
    elif disclosure.processor_code == "hris.bamboohr":
        if disclosure.source_type != "hris_handoff":
            raise _PreparationError("processor_source_mismatch")
        handoff = await session.scalar(
            select(HrisHandoff).where(
                HrisHandoff.id == disclosure.source_id,
                HrisHandoff.tenant_id == request.tenant_id,
            )
        )
        if handoff is None:
            raise _PreparationError("processor_source_unavailable")
        connection = await session.scalar(
            select(HrisConnection).where(
                HrisConnection.id == handoff.hris_connection_id,
                HrisConnection.tenant_id == request.tenant_id,
            )
        )
        if connection is None or connection.provider.value != "bamboohr":
            raise _PreparationError("processor_connection_unavailable")
        credential_reference = connection.credential_reference
    elif disclosure.source_type == "offer_signature":
        signature_request = await session.scalar(
            select(OfferSignatureRequest).where(
                OfferSignatureRequest.id == disclosure.source_id,
                OfferSignatureRequest.tenant_id == request.tenant_id,
            )
        )
        if signature_request is None:
            raise _PreparationError("processor_source_unavailable")
        if f"signature.{signature_request.provider}" != disclosure.processor_code:
            raise _PreparationError("processor_source_mismatch")

    command = CandidateProcessorDeletionCommand(
        deletion_request_id=request.id,
        tenant_id=request.tenant_id,
        processor_code=disclosure.processor_code,
        purpose_code=disclosure.purpose_code,
        source_type=disclosure.source_type,
        source_id=disclosure.source_id,
        external_record_reference=disclosure.external_record_reference,
        idempotency_key=f"candidate-processor-deletion:{request.id}",
        credential_reference=credential_reference,
        calendar_connection_id=calendar_connection_id,
        interview_session_id=interview_session_id,
        external_calendar_id=external_calendar_id,
    )
    # End the read transaction before making provider calls.
    await session.rollback()
    return command


async def _locked_request(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
) -> CandidateProcessorDeletionRequest:
    request = await session.scalar(
        select(CandidateProcessorDeletionRequest)
        .where(
            CandidateProcessorDeletionRequest.id == claim.request_id,
            CandidateProcessorDeletionRequest.tenant_id == claim.tenant_id,
            CandidateProcessorDeletionRequest.status
            == CandidateProcessorDeletionStatus.PROCESSING.value,
            CandidateProcessorDeletionRequest.locked_by == worker_id,
            CandidateProcessorDeletionRequest.version == claim.lease_version,
        )
        .with_for_update()
    )
    if request is None:
        raise CandidateProcessorDeletionLeaseLostError(
            "Processor deletion request lease is no longer owned by this worker."
        )
    return request


async def _complete_request(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
) -> None:
    now = _now()
    context = _worker_context(
        tenant_id=claim.tenant_id,
        worker_id=worker_id,
        request_id=claim.request_id,
    )
    async with transactional(session):
        request = await _locked_request(
            session,
            claim=claim,
            worker_id=worker_id,
        )
        disclosure = await session.scalar(
            select(CandidateProcessorDisclosure)
            .where(
                CandidateProcessorDisclosure.id == request.disclosure_id,
                CandidateProcessorDisclosure.tenant_id == request.tenant_id,
            )
            .with_for_update()
        )
        if disclosure is None:
            raise _PreparationError("processor_source_unavailable")
        disclosure.external_record_reference = None
        request.status = CandidateProcessorDeletionStatus.COMPLETED.value
        request.status_changed_at = now
        request.status_changed_by_subject = context.subject
        request.resolution_code = None
        request.locked_at = None
        request.locked_by = None
        request.last_failure_code = None
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.processor_deletion_outcome_recorded",
            entity_type="candidate_processor_deletion_request",
            entity_id=str(request.id),
            details={
                "processor_code": disclosure.processor_code,
                "status": CandidateProcessorDeletionStatus.COMPLETED.value,
                "attempt_count": request.attempt_count,
                "version": request.version,
            },
        )


async def _fail_request(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
    failure_code: str,
    resolution_code: str,
) -> None:
    now = _now()
    normalized_failure = _failure_code(failure_code)
    context = _worker_context(
        tenant_id=claim.tenant_id,
        worker_id=worker_id,
        request_id=claim.request_id,
    )
    async with transactional(session):
        request = await _locked_request(
            session,
            claim=claim,
            worker_id=worker_id,
        )
        request.status = CandidateProcessorDeletionStatus.EXCEPTION.value
        request.resolution_code = _failure_code(resolution_code)
        request.status_changed_at = now
        request.status_changed_by_subject = context.subject
        request.last_failure_code = normalized_failure
        request.locked_at = None
        request.locked_by = None
        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.processor_deletion_exception_recorded",
            entity_type="candidate_processor_deletion_request",
            entity_id=str(request.id),
            details={
                "status": CandidateProcessorDeletionStatus.EXCEPTION.value,
                "resolution_code": request.resolution_code,
                "failure_code": normalized_failure,
                "attempt_count": request.attempt_count,
                "version": request.version,
            },
        )


async def _retry_request(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
    failure_code: str,
    policy: CandidateProcessorDeletionPolicy,
) -> Literal["retried", "exception"]:
    now = _now()
    normalized_failure = _failure_code(failure_code)
    context = _worker_context(
        tenant_id=claim.tenant_id,
        worker_id=worker_id,
        request_id=claim.request_id,
    )
    async with transactional(session):
        request = await _locked_request(
            session,
            claim=claim,
            worker_id=worker_id,
        )
        request.last_failure_code = normalized_failure
        request.locked_at = None
        request.locked_by = None
        if request.attempt_count >= policy.max_attempts:
            request.status = CandidateProcessorDeletionStatus.EXCEPTION.value
            request.resolution_code = "retry_exhausted"
            request.status_changed_at = now
            request.status_changed_by_subject = context.subject
            outcome: Literal["retried", "exception"] = "exception"
            action = "candidate.processor_deletion_exception_recorded"
            details = {
                "status": CandidateProcessorDeletionStatus.EXCEPTION.value,
                "resolution_code": "retry_exhausted",
                "failure_code": normalized_failure,
                "attempt_count": request.attempt_count,
            }
        else:
            delay = _retry_delay(attempts=request.attempt_count, policy=policy)
            request.status = CandidateProcessorDeletionStatus.PENDING.value
            request.next_attempt_at = now + delay
            outcome = "retried"
            action = "candidate.processor_deletion_retry_scheduled"
            details = {
                "status": CandidateProcessorDeletionStatus.PENDING.value,
                "failure_code": normalized_failure,
                "attempt_count": request.attempt_count,
                "retry_delay_seconds": int(delay.total_seconds()),
            }
        await session.flush()
        details["version"] = request.version
        record_audit_event(
            session,
            context=context,
            action=action,
            entity_type="candidate_processor_deletion_request",
            entity_id=str(request.id),
            details=details,
        )
    return outcome


async def _dispatch_claim(
    session: AsyncSession,
    *,
    claim: _Claim,
    worker_id: str,
    providers: Mapping[str, CandidateProcessorDeletionProvider],
    policy: CandidateProcessorDeletionPolicy,
) -> Literal["completed", "retried", "exception", "lease_lost"]:
    try:
        command = await _build_command(
            session,
            claim=claim,
            worker_id=worker_id,
        )
    except CandidateProcessorDeletionLeaseLostError:
        await session.rollback()
        return "lease_lost"
    except _PreparationError as error:
        await session.rollback()
        try:
            await _fail_request(
                session,
                claim=claim,
                worker_id=worker_id,
                failure_code=error.code,
                resolution_code=error.code,
            )
        except CandidateProcessorDeletionLeaseLostError:
            await session.rollback()
            return "lease_lost"
        return "exception"

    provider = providers.get(command.processor_code)
    if provider is None or provider.processor_code != command.processor_code:
        try:
            await _fail_request(
                session,
                claim=claim,
                worker_id=worker_id,
                failure_code="processor_provider_not_configured",
                resolution_code="provider_not_configured",
            )
        except CandidateProcessorDeletionLeaseLostError:
            await session.rollback()
            return "lease_lost"
        return "exception"

    try:
        await provider.delete_candidate_data(command=command)
    except CandidateProcessorProviderError as error:
        if error.retryable:
            try:
                return await _retry_request(
                    session,
                    claim=claim,
                    worker_id=worker_id,
                    failure_code=error.code,
                    policy=policy,
                )
            except CandidateProcessorDeletionLeaseLostError:
                await session.rollback()
                return "lease_lost"
        try:
            await _fail_request(
                session,
                claim=claim,
                worker_id=worker_id,
                failure_code=error.code,
                resolution_code="provider_terminal_failure",
            )
        except CandidateProcessorDeletionLeaseLostError:
            await session.rollback()
            return "lease_lost"
        return "exception"
    except Exception:  # pylint: disable=broad-exception-caught
        try:
            return await _retry_request(
                session,
                claim=claim,
                worker_id=worker_id,
                failure_code="provider_unexpected_error",
                policy=policy,
            )
        except CandidateProcessorDeletionLeaseLostError:
            await session.rollback()
            return "lease_lost"

    try:
        await _complete_request(
            session,
            claim=claim,
            worker_id=worker_id,
        )
    except CandidateProcessorDeletionLeaseLostError:
        await session.rollback()
        return "lease_lost"
    return "completed"


async def dispatch_candidate_processor_deletions(
    session: AsyncSession,
    *,
    worker_id: str,
    providers: Mapping[str, CandidateProcessorDeletionProvider],
    policy: CandidateProcessorDeletionPolicy = (DEFAULT_CANDIDATE_PROCESSOR_DELETION_POLICY),
) -> CandidateProcessorDeletionDispatchResult:
    """Claim and dispatch one bounded batch of processor deletion requests."""
    claims = await _claim_requests(session, worker_id=worker_id, policy=policy)
    completed = retried = exceptions = lease_lost = 0
    for claim in claims:
        outcome = await _dispatch_claim(
            session,
            claim=claim,
            worker_id=worker_id,
            providers=providers,
            policy=policy,
        )
        if outcome == "completed":
            completed += 1
        elif outcome == "retried":
            retried += 1
        elif outcome == "exception":
            exceptions += 1
        else:
            lease_lost += 1
    return CandidateProcessorDeletionDispatchResult(
        claimed=len(claims),
        completed=completed,
        retried=retried,
        exceptions=exceptions,
        lease_lost=lease_lost,
    )
