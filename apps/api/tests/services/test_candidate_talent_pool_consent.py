"""PostgreSQL tests for explicit talent-pool consent event lifecycle."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_talent_pool_consent import CandidateTalentPoolConsentEvent
from app.db.models.identity import Tenant
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)
from app.services.candidate_privacy import request_candidate_erasure
from app.services.candidate_talent_pool_consent import (
    record_candidate_talent_pool_consent,
)
from app.services.candidate_talent_pool_consent_errors import (
    CandidateTalentPoolConsentAccessDeniedError,
    CandidateTalentPoolConsentNotFoundError,
    CandidateTalentPoolConsentStateError,
    CandidateTalentPoolConsentValidationError,
)
from app.services.candidates import CreateCandidateCommand, create_candidate


def _context(tenant_id: UUID, role: Role, subject: str = "pool-consent-operator") -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=frozenset({role}),
        request_id="pool-consent-test",
    )


async def _create_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Tenant {tenant_id.hex[:12]}",
            slug=f"tenant-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()


async def _create_candidate(session: AsyncSession, tenant_id: UUID) -> Candidate:
    return await create_candidate(
        session,
        context=_context(tenant_id, Role.RECRUITER),
        command=CreateCandidateCommand(
            full_name="Sensitive Candidate Name",
            email=f"pool-{uuid4().hex}@example.com",
            phone=None,
            location=None,
            source="careers_page",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
        ),
    )


async def _record(
    session: AsyncSession,
    *,
    context: TenantContext,
    candidate_id: UUID,
    event_type: CandidateTalentPoolConsentEventType,
    at: datetime,
    notice_version: str | None = "future-roles-v1",
    capture_method: CandidateTalentPoolCaptureMethod = (
        CandidateTalentPoolCaptureMethod.SIGNED_FORM
    ),
) -> CandidateTalentPoolConsentEvent:
    return await record_candidate_talent_pool_consent(
        session,
        context=context,
        candidate_id=candidate_id,
        event_type=event_type,
        capture_method=capture_method,
        notice_version=notice_version,
        recorded_at=at,
    )


@pytest.mark.asyncio
async def test_grant_renewal_withdrawal_are_ordered_and_audited_without_pii(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    context = _context(tenant_id, Role.TENANT_ADMIN)
    start = datetime(2026, 1, 1, tzinfo=UTC)

    granted = await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.GRANTED,
        at=start,
    )
    assert candidate.consent_status is CandidateConsentStatus.UNKNOWN
    renewed = await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.RENEWED,
        at=start + timedelta(days=300),
        notice_version="future-roles-v2",
        capture_method=CandidateTalentPoolCaptureMethod.CANDIDATE_PORTAL,
    )
    withdrawn = await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
        at=start + timedelta(days=301),
        notice_version=None,
        capture_method=CandidateTalentPoolCaptureMethod.EMAIL_CONFIRMATION,
    )
    withdrawal_replay = await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
        at=start + timedelta(days=302),
        notice_version=None,
        capture_method=CandidateTalentPoolCaptureMethod.EMAIL_CONFIRMATION,
    )

    assert (granted.event_version, renewed.event_version, withdrawn.event_version) == (
        1,
        2,
        3,
    )
    assert withdrawal_replay.id == withdrawn.id
    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_type == "candidate_talent_pool_consent_event",
            )
        )
    )
    assert len(audit_events) == 3
    assert all("Sensitive Candidate Name" not in str(event.details) for event in audit_events)
    assert all("@example.com" not in str(event.details) for event in audit_events)


@pytest.mark.asyncio
async def test_consent_transitions_require_grant_before_renew_or_withdraw(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    context = _context(tenant_id, Role.RECRUITER)
    at = datetime(2026, 2, 1, tzinfo=UTC)

    with pytest.raises(CandidateTalentPoolConsentStateError):
        await _record(
            session,
            context=context,
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.RENEWED,
            at=at,
        )
    with pytest.raises(CandidateTalentPoolConsentStateError):
        await _record(
            session,
            context=context,
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.WITHDRAWN,
            at=at,
            notice_version=None,
            capture_method=CandidateTalentPoolCaptureMethod.EMAIL_CONFIRMATION,
        )

    await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.GRANTED,
        at=at,
    )
    with pytest.raises(CandidateTalentPoolConsentStateError):
        await _record(
            session,
            context=context,
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.GRANTED,
            at=at + timedelta(seconds=1),
        )


@pytest.mark.asyncio
async def test_consent_requires_allowed_role_and_tenant_owned_candidate(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    await _create_tenant(session, other_tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    at = datetime(2026, 3, 1, tzinfo=UTC)

    with pytest.raises(CandidateTalentPoolConsentAccessDeniedError):
        await _record(
            session,
            context=_context(tenant_id, Role.ANALYST),
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.GRANTED,
            at=at,
        )
    with pytest.raises(CandidateTalentPoolConsentNotFoundError):
        await _record(
            session,
            context=_context(other_tenant_id, Role.TENANT_ADMIN),
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.GRANTED,
            at=at,
        )


@pytest.mark.asyncio
async def test_grant_requires_notice_version_and_erasure_withdraws_active_consent(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    context = _context(tenant_id, Role.PEOPLE_OPERATIONS)
    at = datetime(2026, 4, 1, tzinfo=UTC)

    with pytest.raises(CandidateTalentPoolConsentValidationError):
        await _record(
            session,
            context=context,
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.GRANTED,
            at=at,
            notice_version="  ",
        )

    await _record(
        session,
        context=context,
        candidate_id=candidate.id,
        event_type=CandidateTalentPoolConsentEventType.GRANTED,
        at=at,
    )
    await request_candidate_erasure(
        session,
        context=context,
        candidate_id=candidate.id,
    )
    latest = await session.scalar(
        select(CandidateTalentPoolConsentEvent)
        .where(CandidateTalentPoolConsentEvent.candidate_id == candidate.id)
        .order_by(CandidateTalentPoolConsentEvent.event_version.desc())
        .limit(1)
    )
    assert latest is not None
    assert latest.event_type is CandidateTalentPoolConsentEventType.WITHDRAWN
    assert latest.capture_method is CandidateTalentPoolCaptureMethod.ERASURE_REQUEST


@pytest.mark.asyncio
async def test_erasure_request_method_cannot_be_used_as_a_grant(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    with pytest.raises(CandidateTalentPoolConsentValidationError):
        await _record(
            session,
            context=_context(tenant_id, Role.TENANT_ADMIN),
            candidate_id=candidate.id,
            event_type=CandidateTalentPoolConsentEventType.GRANTED,
            at=datetime(2026, 5, 1, tzinfo=UTC),
            capture_method=CandidateTalentPoolCaptureMethod.ERASURE_REQUEST,
        )
