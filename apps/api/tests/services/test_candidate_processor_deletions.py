"""PostgreSQL tests for external processor deletion tracking."""

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_processor import (
    CandidateProcessorDeletionRequest,
    CandidateProcessorDisclosure,
)
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.identity import Tenant
from app.domains.candidates.enums import (
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.processor_data import (
    CandidateProcessorDeletionStatus,
    CandidateProcessorDisclosureSource,
    CandidateProcessorPurpose,
)
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.services.candidate_privacy import request_candidate_erasure
from app.services.candidate_processor_deletions import (
    record_candidate_processor_deletion_outcome,
    record_candidate_processor_disclosure,
)
from app.services.candidate_processor_errors import (
    CandidateProcessorDeletionAccessDeniedError,
    CandidateProcessorDeletionNotFoundError,
    CandidateProcessorDeletionValidationError,
    CandidateProcessorDeletionVersionConflictError,
    CandidateProcessorDisclosureConflictError,
)
from app.services.candidate_retention_errors import CandidateRetentionHoldActiveError


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject="privacy-operator",
        roles=roles,
        request_id="processor-deletion-test",
    )


async def _seed_candidate(session: AsyncSession) -> tuple[UUID, Candidate]:
    tenant_id = uuid4()
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Processor Tenant {tenant_id.hex[:12]}",
            slug=f"processor-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()
    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Private Candidate",
        email=f"private-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"private-{tenant_id.hex[:12]}@example.test",
        phone="+254700000001",
        source="employee_referral",
        source_metadata={"confidential": "value"},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="processor-test",
    )
    session.add(candidate)
    await session.flush()
    return tenant_id, candidate


async def _record_disclosure(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    source_id: UUID | None = None,
) -> CandidateProcessorDisclosure:
    return await record_candidate_processor_disclosure(
        session,
        context=_context(tenant_id),
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        processor_code="signature.example_provider",
        purpose=CandidateProcessorPurpose.OFFER_SIGNATURE,
        source=CandidateProcessorDisclosureSource.OFFER_SIGNATURE,
        source_id=source_id or uuid4(),
        external_record_reference="opaque-envelope-123",
    )


@pytest.mark.asyncio
async def test_disclosure_is_idempotent_and_rejects_conflicting_source(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    source_id = uuid4()

    first = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        source_id=source_id,
    )
    second = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        source_id=source_id,
    )

    assert first.id == second.id
    assert len(list(await session.scalars(select(CandidateProcessorDisclosure)))) == 1
    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.processor_disclosed"
            )
        )
    )
    assert len(audit_events) == 1
    assert audit_events[0].details == {
        "processor_code": "signature.example_provider",
        "purpose_code": CandidateProcessorPurpose.OFFER_SIGNATURE.value,
        "source_type": CandidateProcessorDisclosureSource.OFFER_SIGNATURE.value,
    }
    assert "Private Candidate" not in str(audit_events[0].details)
    assert "opaque-envelope-123" not in str(audit_events[0].details)

    with pytest.raises(CandidateProcessorDisclosureConflictError):
        await record_candidate_processor_disclosure(
            session,
            context=_context(tenant_id),
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            processor_code="signature.another_provider",
            purpose=CandidateProcessorPurpose.OFFER_SIGNATURE,
            source=CandidateProcessorDisclosureSource.OFFER_SIGNATURE,
            source_id=source_id,
            external_record_reference="opaque-envelope-123",
        )


@pytest.mark.asyncio
async def test_erasure_atomically_queues_one_work_item_per_disclosure(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    first = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    second = await record_candidate_processor_disclosure(
        session,
        context=_context(tenant_id),
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        processor_code="hris.bamboohr",
        purpose=CandidateProcessorPurpose.ONBOARDING_HANDOFF,
        source=CandidateProcessorDisclosureSource.HRIS_HANDOFF,
        source_id=uuid4(),
        external_record_reference="opaque-employee-456",
    )

    await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )
    # A repeated request is a no-op; uniqueness is additionally enforced in DB.
    await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    requests = list(
        await session.scalars(
            select(CandidateProcessorDeletionRequest).order_by(
                CandidateProcessorDeletionRequest.disclosure_id
            )
        )
    )
    assert len(requests) == 2
    assert {request.disclosure_id for request in requests} == {first.id, second.id}
    assert {request.status for request in requests} == {
        CandidateProcessorDeletionStatus.PENDING.value
    }

    erasure_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate.erasure_requested",
            AuditEvent.entity_id == str(candidate.id),
        )
    )
    assert erasure_event is not None
    assert erasure_event.details == {
        "document_count": 0,
        "processor_deletion_request_count": 2,
        "privacy_status": "erased",
    }

    deletion_audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.processor_deletion_requested"
            )
        )
    )
    assert len(deletion_audits) == 2
    assert all(
        "Private Candidate" not in str(event.details)
        and "opaque-" not in str(event.details)
        for event in deletion_audits
    )


@pytest.mark.asyncio
async def test_active_hold_prevents_processor_deletion_requests(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    disclosure = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    session.add(
        CandidateRetentionHold(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            reason=CandidateRetentionHoldReason.LEGAL_CLAIM,
            created_by_subject="privacy-operator",
        )
    )
    await session.flush()

    with pytest.raises(CandidateRetentionHoldActiveError):
        await request_candidate_erasure(
            session,
            context=_context(tenant_id),
            candidate_id=candidate.id,
        )

    requests = list(
        await session.scalars(
            select(CandidateProcessorDeletionRequest).where(
                CandidateProcessorDeletionRequest.disclosure_id == disclosure.id
            )
        )
    )
    assert not requests
    assert candidate.privacy_status is CandidatePrivacyStatus.ACTIVE


@pytest.mark.asyncio
async def test_late_disclosure_after_erasure_is_queued_immediately(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )

    disclosure = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    request = await session.scalar(
        select(CandidateProcessorDeletionRequest).where(
            CandidateProcessorDeletionRequest.disclosure_id == disclosure.id
        )
    )
    assert request is not None
    assert request.status == CandidateProcessorDeletionStatus.PENDING.value


@pytest.mark.asyncio
async def test_concurrent_erasure_creates_only_one_processor_deletion_request(
    session: AsyncSession,
    database_engine: AsyncEngine,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    disclosure = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    await session.commit()

    session_factory = async_sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    async def erase() -> None:
        async with session_factory() as worker_session:
            await request_candidate_erasure(
                worker_session,
                context=_context(tenant_id),
                candidate_id=candidate.id,
            )
            await worker_session.commit()

    await asyncio.gather(erase(), erase())

    requests = list(
        await session.scalars(
            select(CandidateProcessorDeletionRequest).where(
                CandidateProcessorDeletionRequest.disclosure_id == disclosure.id
            )
        )
    )
    audits = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.processor_deletion_requested",
            )
        )
    )
    assert len(requests) == 1
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_deletion_outcome_enforces_tenant_role_version_and_clears_reference(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    other_tenant_id = uuid4()
    session.add(
        Tenant(
            id=other_tenant_id,
            name=f"Other Processor Tenant {other_tenant_id.hex[:12]}",
            slug=f"other-processor-{other_tenant_id.hex[:12]}",
        )
    )
    await session.flush()
    disclosure = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )
    request = await session.scalar(
        select(CandidateProcessorDeletionRequest).where(
            CandidateProcessorDeletionRequest.disclosure_id == disclosure.id
        )
    )
    assert request is not None

    with pytest.raises(CandidateProcessorDeletionNotFoundError):
        await record_candidate_processor_deletion_outcome(
            session,
            context=_context(other_tenant_id),
            deletion_request_id=request.id,
            expected_version=request.version,
            status=CandidateProcessorDeletionStatus.COMPLETED,
        )
    with pytest.raises(CandidateProcessorDeletionAccessDeniedError):
        await record_candidate_processor_deletion_outcome(
            session,
            context=_context(tenant_id, frozenset({Role.RECRUITER})),
            deletion_request_id=request.id,
            expected_version=request.version,
            status=CandidateProcessorDeletionStatus.COMPLETED,
        )
    with pytest.raises(CandidateProcessorDeletionVersionConflictError):
        await record_candidate_processor_deletion_outcome(
            session,
            context=_context(tenant_id),
            deletion_request_id=request.id,
            expected_version=request.version + 1,
            status=CandidateProcessorDeletionStatus.COMPLETED,
        )
    with pytest.raises(CandidateProcessorDeletionValidationError):
        await record_candidate_processor_deletion_outcome(
            session,
            context=_context(tenant_id),
            deletion_request_id=request.id,
            expected_version=request.version,
            status=CandidateProcessorDeletionStatus.EXCEPTION,
        )

    completed = await record_candidate_processor_deletion_outcome(
        session,
        context=_context(tenant_id, frozenset({Role.PEOPLE_OPERATIONS})),
        deletion_request_id=request.id,
        expected_version=request.version,
        status=CandidateProcessorDeletionStatus.COMPLETED,
    )
    await session.refresh(disclosure)

    assert completed.status == CandidateProcessorDeletionStatus.COMPLETED.value
    assert completed.version > 1
    assert disclosure.external_record_reference is None
    completion_audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate.processor_deletion_outcome_recorded",
            AuditEvent.entity_id == str(request.id),
        )
    )
    assert completion_audit is not None
    assert completion_audit.details == {
        "processor_code": "signature.example_provider",
        "status": CandidateProcessorDeletionStatus.COMPLETED.value,
        "resolution_code": None,
        "version": completed.version,
    }


@pytest.mark.asyncio
async def test_exception_can_be_resolved_and_terminal_status_cannot_be_reopened(
    session: AsyncSession,
) -> None:
    tenant_id, candidate = await _seed_candidate(session)
    disclosure = await _record_disclosure(
        session,
        tenant_id=tenant_id,
        candidate_id=candidate.id,
    )
    await request_candidate_erasure(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
    )
    request = await session.scalar(
        select(CandidateProcessorDeletionRequest).where(
            CandidateProcessorDeletionRequest.disclosure_id == disclosure.id
        )
    )
    assert request is not None

    exception = await record_candidate_processor_deletion_outcome(
        session,
        context=_context(tenant_id),
        deletion_request_id=request.id,
        expected_version=request.version,
        status=CandidateProcessorDeletionStatus.EXCEPTION,
        resolution_code="provider_retention_window",
    )
    completed = await record_candidate_processor_deletion_outcome(
        session,
        context=_context(tenant_id),
        deletion_request_id=request.id,
        expected_version=exception.version,
        status=CandidateProcessorDeletionStatus.COMPLETED,
    )
    assert completed.status == CandidateProcessorDeletionStatus.COMPLETED.value

    with pytest.raises(CandidateProcessorDeletionValidationError):
        await record_candidate_processor_deletion_outcome(
            session,
            context=_context(tenant_id),
            deletion_request_id=request.id,
            expected_version=completed.version,
            status=CandidateProcessorDeletionStatus.PENDING,
        )
