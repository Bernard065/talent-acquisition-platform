"""Transactional state changes for reliable HRIS handoff dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.application import Application
from app.db.models.hris import HrisConnection, HrisHandoff
from app.db.transactions import transactional
from app.domains.candidates.processor_data import (
    CandidateProcessorDisclosureSource,
    CandidateProcessorPurpose,
)
from app.domains.hris.enums import HrisHandoffStatus
from app.domains.hris.transitions import validate_hris_handoff_transition
from app.services.audit import record_audit_event
from app.services.candidate_processor_deletions import (
    record_candidate_processor_disclosure,
)
from app.services.hris_handoff_errors import (
    HrisHandoffNotFoundError,
    HrisHandoffValidationError,
    HrisHandoffVersionConflictError,
)

_MAX_EXTERNAL_REFERENCE_LENGTH = 500
_MAX_FAILURE_CODE_LENGTH = 100


def _validate_failure_code(failure_code: str) -> str:
    """Accept only classified, non-sensitive error codes."""
    normalized = failure_code.strip().lower()

    if (
        not normalized
        or len(normalized) > _MAX_FAILURE_CODE_LENGTH
        or not all(
            character.islower()
            or character.isdigit()
            or character == "_"
            for character in normalized
        )
    ):
        raise HrisHandoffValidationError("HRIS handoff failure code is invalid.")

    return normalized


def _validate_expected_version(
    handoff: HrisHandoff,
    expected_version: int,
) -> None:
    """Reject stale worker writes before mutating a locked row."""
    if expected_version < 1:
        raise HrisHandoffValidationError(
            "Expected HRIS handoff version must be at least one."
        )

    if handoff.version != expected_version:
        raise HrisHandoffVersionConflictError(
            "HRIS handoff has changed; reload before retrying."
        )


async def _load_handoff_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
) -> HrisHandoff:
    """Load and lock one handoff within the worker tenant."""
    handoff = await session.scalar(
        select(HrisHandoff)
        .where(
            HrisHandoff.id == handoff_id,
            HrisHandoff.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )

    if handoff is None:
        raise HrisHandoffNotFoundError("HRIS handoff was not found.")

    return handoff


async def _reload_detached_handoff(
    session: AsyncSession,
    *,
    handoff_id: UUID,
) -> HrisHandoff:
    """Return a refreshed handoff safe to inspect after transaction completion."""
    handoff = await session.get(HrisHandoff, handoff_id)
    if handoff is None:
        raise HrisHandoffNotFoundError("HRIS handoff was not found.")

    await session.refresh(handoff)
    session.expunge(handoff)
    return handoff


async def prepare_hris_handoff_dispatch(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
) -> HrisHandoff:
    """
    Make one handoff ready for provider dispatch.

    A recovered worker may see `processing` after a crash between provider
    submission and outbox acknowledgement. It is intentionally allowed to
    continue with the stable external idempotency key.
    """

    async with transactional(session):
        handoff = await _load_handoff_for_update(
            session,
            context=context,
            handoff_id=handoff_id,
        )

        if handoff.status in {
            HrisHandoffStatus.PENDING,
            HrisHandoffStatus.RETRYABLE_FAILED,
        }:
            previous_status = handoff.status
            validate_hris_handoff_transition(
                previous_status,
                HrisHandoffStatus.PROCESSING,
            )

            handoff.status = HrisHandoffStatus.PROCESSING
            handoff.last_attempt_at = datetime.now(UTC)
            handoff.attempt_count += 1
            handoff.last_error_code = None

            await session.flush()

            record_audit_event(
                session,
                context=context,
                action="hris_handoff.dispatch_started",
                entity_type="hris_handoff",
                entity_id=str(handoff.id),
                details={
                    "from_status": previous_status.value,
                    "status": handoff.status.value,
                    "attempt_count": handoff.attempt_count,
                    "version": handoff.version,
                },
            )
        elif handoff.status is not HrisHandoffStatus.PROCESSING:
            raise HrisHandoffValidationError(
                "HRIS handoff is not dispatchable in its current state."
            )

        await session.flush()

    return await _reload_detached_handoff(session, handoff_id=handoff_id)


async def mark_hris_handoff_succeeded(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
    expected_version: int,
    external_employee_reference: str,
) -> HrisHandoff:
    """Persist one successful, idempotent HRIS employee handoff."""

    reference = external_employee_reference.strip()
    if not reference or len(reference) > _MAX_EXTERNAL_REFERENCE_LENGTH:
        raise HrisHandoffValidationError(
            "External HRIS employee reference is invalid."
        )

    async with transactional(session):
        handoff = await _load_handoff_for_update(
            session,
            context=context,
            handoff_id=handoff_id,
        )
        _validate_expected_version(handoff, expected_version)

        validate_hris_handoff_transition(
            handoff.status,
            HrisHandoffStatus.SUCCEEDED,
        )

        previous_status = handoff.status
        candidate_id = await session.scalar(
            select(Application.candidate_id).where(
                Application.id == handoff.application_id,
                Application.tenant_id == context.tenant_id,
            )
        )
        provider = await session.scalar(
            select(HrisConnection.provider).where(
                HrisConnection.id == handoff.hris_connection_id,
                HrisConnection.tenant_id == context.tenant_id,
            )
        )
        if candidate_id is None or provider is None:
            raise HrisHandoffNotFoundError("HRIS handoff is incomplete.")

        handoff.status = HrisHandoffStatus.SUCCEEDED
        handoff.external_employee_reference = reference
        handoff.succeeded_at = datetime.now(UTC)
        handoff.last_error_code = None

        await record_candidate_processor_disclosure(
            session,
            context=context,
            tenant_id=context.tenant_id,
            candidate_id=candidate_id,
            processor_code=f"hris.{provider.value}",
            purpose=CandidateProcessorPurpose.ONBOARDING_HANDOFF,
            source=CandidateProcessorDisclosureSource.HRIS_HANDOFF,
            source_id=handoff.id,
            external_record_reference=reference,
        )

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="hris_handoff.succeeded",
            entity_type="hris_handoff",
            entity_id=str(handoff.id),
            details={
                "from_status": previous_status.value,
                "status": handoff.status.value,
                "attempt_count": handoff.attempt_count,
                "version": handoff.version,
            },
        )
        await session.flush()

    return await _reload_detached_handoff(session, handoff_id=handoff_id)


async def mark_hris_handoff_retryable_failure(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
    expected_version: int,
    failure_code: str,
) -> HrisHandoff:
    """Persist a classified retryable provider failure."""

    normalized_failure_code = _validate_failure_code(failure_code)

    async with transactional(session):
        handoff = await _load_handoff_for_update(
            session,
            context=context,
            handoff_id=handoff_id,
        )
        _validate_expected_version(handoff, expected_version)

        validate_hris_handoff_transition(
            handoff.status,
            HrisHandoffStatus.RETRYABLE_FAILED,
        )

        previous_status = handoff.status
        handoff.status = HrisHandoffStatus.RETRYABLE_FAILED
        handoff.last_error_code = normalized_failure_code

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="hris_handoff.retryable_failed",
            entity_type="hris_handoff",
            entity_id=str(handoff.id),
            details={
                "from_status": previous_status.value,
                "status": handoff.status.value,
                "failure_code": normalized_failure_code,
                "attempt_count": handoff.attempt_count,
                "version": handoff.version,
            },
        )
        await session.flush()

    return await _reload_detached_handoff(session, handoff_id=handoff_id)


async def mark_hris_handoff_failed(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
    expected_version: int,
    failure_code: str,
) -> HrisHandoff:
    """Persist a terminal, classified HRIS handoff failure."""

    normalized_failure_code = _validate_failure_code(failure_code)

    async with transactional(session):
        handoff = await _load_handoff_for_update(
            session,
            context=context,
            handoff_id=handoff_id,
        )
        _validate_expected_version(handoff, expected_version)

        validate_hris_handoff_transition(
            handoff.status,
            HrisHandoffStatus.FAILED,
        )

        previous_status = handoff.status
        handoff.status = HrisHandoffStatus.FAILED
        handoff.last_error_code = normalized_failure_code

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="hris_handoff.failed",
            entity_type="hris_handoff",
            entity_id=str(handoff.id),
            details={
                "from_status": previous_status.value,
                "status": handoff.status.value,
                "failure_code": normalized_failure_code,
                "attempt_count": handoff.attempt_count,
                "version": handoff.version,
            },
        )
        await session.flush()

    return await _reload_detached_handoff(session, handoff_id=handoff_id)
