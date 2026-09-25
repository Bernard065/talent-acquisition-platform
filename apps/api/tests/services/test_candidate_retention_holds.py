"""PostgreSQL tests for candidate retention holds and erasure protection."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.domains.candidates.enums import (
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.services.candidate_privacy import request_candidate_erasure
from app.services.candidate_retention_errors import (
    CandidateRetentionAccessDeniedError,
    CandidateRetentionHoldActiveError,
    CandidateRetentionHoldNotFoundError,
    CandidateRetentionHoldStateError,
)
from app.services.candidate_retention_holds import (
    place_candidate_retention_hold,
    release_candidate_retention_hold,
)
from app.services.candidates import CreateCandidateCommand, create_candidate


def _context(tenant_id: UUID, role: Role, subject: str = "hold-operator") -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=frozenset({role}),
        request_id="retention-hold-test",
    )


async def _tenant(session: AsyncSession, tenant_id: UUID) -> None:
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()


async def _candidate(session: AsyncSession, tenant_id: UUID):
    return await create_candidate(
        session,
        context=_context(tenant_id, Role.RECRUITER),
        command=CreateCandidateCommand(
            full_name="Private Candidate Name",
            email=f"candidate-{uuid4().hex}@example.com",
            phone=None,
            location=None,
            source="careers_page",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
        ),
    )


@pytest.mark.asyncio
async def test_hold_placement_is_idempotent_and_release_is_audited_once(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _tenant(session, tenant_id)
    candidate = await _candidate(session, tenant_id)
    context = _context(tenant_id, Role.TENANT_ADMIN)
    moment = datetime(2026, 9, 25, 10, tzinfo=UTC)

    hold = await place_candidate_retention_hold(
        session,
        context=context,
        candidate_id=candidate.id,
        reason=CandidateRetentionHoldReason.LEGAL_CLAIM,
        now=moment,
    )
    replayed = await place_candidate_retention_hold(
        session,
        context=context,
        candidate_id=candidate.id,
        reason=CandidateRetentionHoldReason.LEGAL_CLAIM,
        now=moment,
    )
    assert replayed.id == hold.id

    await release_candidate_retention_hold(
        session, context=context, hold_id=hold.id, now=moment
    )
    await release_candidate_retention_hold(
        session, context=context, hold_id=hold.id, now=moment
    )
    assert hold.released_at == moment
    assert hold.released_by_subject == context.subject

    events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_type == "candidate_retention_hold",
            )
        )
    )
    assert [event.action for event in events] == [
        "candidate.retention_hold_placed",
        "candidate.retention_hold_released",
    ]
    assert all("Private Candidate Name" not in str(event.details) for event in events)
    assert all("example.com" not in str(event.details) for event in events)


@pytest.mark.asyncio
async def test_active_hold_blocks_erasure_until_released(session: AsyncSession) -> None:
    tenant_id = uuid4()
    await _tenant(session, tenant_id)
    candidate = await _candidate(session, tenant_id)
    admin = _context(tenant_id, Role.PEOPLE_OPERATIONS)
    hold = await place_candidate_retention_hold(
        session,
        context=admin,
        candidate_id=candidate.id,
        reason=CandidateRetentionHoldReason.STATUTORY_OBLIGATION,
    )

    with pytest.raises(CandidateRetentionHoldActiveError):
        await request_candidate_erasure(
            session,
            context=admin,
            candidate_id=candidate.id,
        )
    assert candidate.email.endswith("@example.com")

    await release_candidate_retention_hold(session, context=admin, hold_id=hold.id)
    erased = await request_candidate_erasure(
        session,
        context=admin,
        candidate_id=candidate.id,
    )
    assert erased.email.endswith("@privacy.invalid")


@pytest.mark.asyncio
async def test_hold_access_and_candidate_state_are_scoped(session: AsyncSession) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _tenant(session, tenant_id)
    await _tenant(session, other_tenant_id)
    candidate = await _candidate(session, tenant_id)

    with pytest.raises(CandidateRetentionAccessDeniedError):
        await place_candidate_retention_hold(
            session,
            context=_context(tenant_id, Role.RECRUITER),
            candidate_id=candidate.id,
            reason=CandidateRetentionHoldReason.OTHER_EVIDENCE,
        )
    with pytest.raises(CandidateRetentionHoldNotFoundError):
        await place_candidate_retention_hold(
            session,
            context=_context(other_tenant_id, Role.TENANT_ADMIN),
            candidate_id=candidate.id,
            reason=CandidateRetentionHoldReason.OTHER_EVIDENCE,
        )

    hold = await place_candidate_retention_hold(
        session,
        context=_context(tenant_id, Role.TENANT_ADMIN),
        candidate_id=candidate.id,
        reason=CandidateRetentionHoldReason.OTHER_EVIDENCE,
    )
    with pytest.raises(CandidateRetentionHoldNotFoundError):
        await release_candidate_retention_hold(
            session,
            context=_context(other_tenant_id, Role.TENANT_ADMIN),
            hold_id=hold.id,
        )

    candidate.privacy_status = CandidatePrivacyStatus.ERASED
    candidate.erasure_requested_at = datetime.now(UTC)
    candidate.erased_at = datetime.now(UTC)
    await session.flush()
    with pytest.raises(CandidateRetentionHoldStateError):
        await place_candidate_retention_hold(
            session,
            context=_context(tenant_id, Role.TENANT_ADMIN),
            candidate_id=candidate.id,
            reason=CandidateRetentionHoldReason.REGULATORY_REQUEST,
        )
