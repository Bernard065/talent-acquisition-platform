"""Tenant-safe recording of processor disclosures and deletion outcomes."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.candidate import Candidate
from app.db.models.candidate_processor import (
    CandidateProcessorDeletionRequest,
    CandidateProcessorDisclosure,
)
from app.db.transactions import transactional
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.processor_data import (
    CandidateProcessorDeletionStatus,
    CandidateProcessorDisclosureSource,
    CandidateProcessorPurpose,
)
from app.services.audit import record_audit_event
from app.services.candidate_processor_errors import (
    CandidateProcessorDeletionAccessDeniedError,
    CandidateProcessorDeletionNotFoundError,
    CandidateProcessorDeletionValidationError,
    CandidateProcessorDeletionVersionConflictError,
    CandidateProcessorDisclosureConflictError,
)

_DELETION_MANAGEMENT_ROLES = frozenset({Role.TENANT_ADMIN, Role.PEOPLE_OPERATIONS})
_SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


def _safe_identifier(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not _SAFE_IDENTIFIER.fullmatch(normalized):
        raise CandidateProcessorDeletionValidationError(f"{label} is invalid.")
    return normalized


async def record_candidate_processor_disclosure(
    session: AsyncSession,
    *,
    context: TenantContext,
    tenant_id: UUID,
    candidate_id: UUID,
    processor_code: str,
    purpose: CandidateProcessorPurpose,
    source: CandidateProcessorDisclosureSource,
    source_id: UUID,
    external_record_reference: str,
) -> CandidateProcessorDisclosure:
    """Record one successful candidate-linked external disclosure idempotently.

    The source record is the idempotency boundary: retrying a successful,
    provider-idempotent operation cannot create a second disclosure row.
    No candidate profile data is accepted by this function.
    """
    normalized_processor = _safe_identifier(processor_code, label="Processor")
    if context.tenant_id != tenant_id:
        raise CandidateProcessorDeletionValidationError(
            "Disclosure tenant does not match the verified context."
        )
    reference = external_record_reference.strip()
    if not reference or len(reference) > 500:
        raise CandidateProcessorDeletionValidationError(
            "External record reference is invalid."
        )

    async with transactional(session):
        candidate = await session.scalar(
            select(Candidate)
            .where(
                Candidate.id == candidate_id,
                Candidate.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if candidate is None:
            raise CandidateProcessorDisclosureConflictError(
                "Processor disclosure candidate was not found."
            )

        inserted_id = await session.scalar(
            insert(CandidateProcessorDisclosure)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                candidate_id=candidate_id,
                processor_code=normalized_processor,
                purpose_code=purpose.value,
                source_type=source.value,
                source_id=source_id,
                external_record_reference=reference,
            )
            .on_conflict_do_nothing(
                constraint="uq_candidate_processor_disclosures_source"
            )
            .returning(CandidateProcessorDisclosure.id)
        )
        disclosure = await session.scalar(
            select(CandidateProcessorDisclosure).where(
                CandidateProcessorDisclosure.tenant_id == tenant_id,
                CandidateProcessorDisclosure.source_type == source.value,
                CandidateProcessorDisclosure.source_id == source_id,
            )
        )
        if disclosure is None:
            raise RuntimeError("Processor disclosure could not be persisted.")

        if (
            disclosure.candidate_id != candidate_id
            or disclosure.processor_code != normalized_processor
            or disclosure.purpose_code != purpose.value
            or disclosure.external_record_reference != reference
        ):
            raise CandidateProcessorDisclosureConflictError(
                "Processor disclosure source already has different metadata."
            )

        if inserted_id is not None:
            record_audit_event(
                session,
                context=context,
                action="candidate.processor_disclosed",
                entity_type="candidate_processor_disclosure",
                entity_id=str(disclosure.id),
                details={
                    "processor_code": normalized_processor,
                    "purpose_code": purpose.value,
                    "source_type": source.value,
                },
            )

            # If an external operation completed after erasure began, queue its
            # deletion immediately. The candidate row lock serializes this
            # path with the erasure transaction and prevents an untracked race.
            if candidate.privacy_status is not CandidatePrivacyStatus.ACTIVE:
                await _create_deletion_request(
                    session,
                    context=context,
                    disclosure=disclosure,
                )

        return disclosure


async def _create_deletion_request(
    session: AsyncSession,
    *,
    context: TenantContext,
    disclosure: CandidateProcessorDisclosure,
) -> UUID | None:
    """Insert an idempotent pending request and audit only safe metadata."""
    request_id = await session.scalar(
        insert(CandidateProcessorDeletionRequest)
        .values(
            id=uuid4(),
            tenant_id=context.tenant_id,
            disclosure_id=disclosure.id,
            status=CandidateProcessorDeletionStatus.PENDING.value,
            version=1,
        )
        .on_conflict_do_nothing(
            constraint="uq_candidate_processor_deletion_disclosure"
        )
        .returning(CandidateProcessorDeletionRequest.id)
    )
    if request_id is not None:
        record_audit_event(
            session,
            context=context,
            action="candidate.processor_deletion_requested",
            entity_type="candidate_processor_deletion_request",
            entity_id=str(request_id),
            details={
                "processor_code": disclosure.processor_code,
                "purpose_code": disclosure.purpose_code,
                "status": CandidateProcessorDeletionStatus.PENDING.value,
            },
        )
    return request_id


async def queue_candidate_processor_deletions(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
) -> int:
    """Create one durable deletion request per recorded processor disclosure.

    Called from candidate erasure's transaction. The unique disclosure key
    makes queueing safe on retries, and processor/provider calls are purposely
    not made here.
    """
    disclosures = list(
        await session.scalars(
            select(CandidateProcessorDisclosure)
            .where(
                CandidateProcessorDisclosure.tenant_id == context.tenant_id,
                CandidateProcessorDisclosure.candidate_id == candidate_id,
            )
            .order_by(CandidateProcessorDisclosure.id)
            .with_for_update()
        )
    )
    created_count = 0
    for disclosure in disclosures:
        request_id = await _create_deletion_request(
            session,
            context=context,
            disclosure=disclosure,
        )
        if request_id is not None:
            created_count += 1

    return created_count


async def record_candidate_processor_deletion_outcome(
    session: AsyncSession,
    *,
    context: TenantContext,
    deletion_request_id: UUID,
    expected_version: int,
    status: CandidateProcessorDeletionStatus,
    resolution_code: str | None = None,
) -> CandidateProcessorDeletionRequest:
    """Record a reviewed completion, exception, or waiver for a deletion request."""
    if context.roles.isdisjoint(_DELETION_MANAGEMENT_ROLES):
        raise CandidateProcessorDeletionAccessDeniedError(
            "Caller cannot manage processor deletion outcomes."
        )

    if status is CandidateProcessorDeletionStatus.PENDING:
        raise CandidateProcessorDeletionValidationError(
            "A deletion outcome cannot return to pending."
        )

    normalized_code: str | None = None
    if status in {
        CandidateProcessorDeletionStatus.EXCEPTION,
        CandidateProcessorDeletionStatus.WAIVED,
    }:
        if resolution_code is None:
            raise CandidateProcessorDeletionValidationError(
                "Exception and waiver outcomes require a controlled resolution code."
            )
        normalized_code = _safe_identifier(resolution_code, label="Resolution code")
    elif resolution_code is not None:
        raise CandidateProcessorDeletionValidationError(
            "A completed outcome must not include a resolution code."
        )

    async with transactional(session):
        request = await session.scalar(
            select(CandidateProcessorDeletionRequest)
            .where(
                CandidateProcessorDeletionRequest.id == deletion_request_id,
                CandidateProcessorDeletionRequest.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if request is None:
            raise CandidateProcessorDeletionNotFoundError(
                "Processor deletion request was not found."
            )
        if expected_version < 1 or request.version != expected_version:
            raise CandidateProcessorDeletionVersionConflictError(
                "Processor deletion request changed; reload before retrying."
            )

        current_status = CandidateProcessorDeletionStatus(request.status)
        allowed = {
            CandidateProcessorDeletionStatus.PENDING: {
                CandidateProcessorDeletionStatus.COMPLETED,
                CandidateProcessorDeletionStatus.EXCEPTION,
                CandidateProcessorDeletionStatus.WAIVED,
            },
            CandidateProcessorDeletionStatus.EXCEPTION: {
                CandidateProcessorDeletionStatus.COMPLETED,
                CandidateProcessorDeletionStatus.WAIVED,
            },
            CandidateProcessorDeletionStatus.COMPLETED: set(),
            CandidateProcessorDeletionStatus.WAIVED: set(),
        }
        if status not in allowed[current_status]:
            raise CandidateProcessorDeletionValidationError(
                "Processor deletion outcome is invalid from the current status."
            )

        request.status = status.value
        request.resolution_code = normalized_code
        request.status_changed_at = datetime.now(UTC)
        request.status_changed_by_subject = context.subject

        disclosure = await session.scalar(
            select(CandidateProcessorDisclosure)
            .where(
                CandidateProcessorDisclosure.id == request.disclosure_id,
                CandidateProcessorDisclosure.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if disclosure is None:
            raise RuntimeError("Processor deletion disclosure was not found.")
        if status is CandidateProcessorDeletionStatus.COMPLETED:
            # The provider's opaque record reference is no longer needed once
            # deletion is confirmed; clear it in the same transaction.
            disclosure.external_record_reference = None

        await session.flush()
        record_audit_event(
            session,
            context=context,
            action="candidate.processor_deletion_outcome_recorded",
            entity_type="candidate_processor_deletion_request",
            entity_id=str(request.id),
            details={
                "processor_code": disclosure.processor_code,
                "status": status.value,
                "resolution_code": normalized_code,
                "version": request.version,
            },
        )
        await session.flush()

    return request
