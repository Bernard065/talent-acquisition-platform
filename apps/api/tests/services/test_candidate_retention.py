"""PostgreSQL coverage for versioned policy lifecycle and dry-run evaluation."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_hold import CandidateRetentionHold
from app.db.models.candidate_talent_pool_consent import CandidateTalentPoolConsentEvent
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.retention import CandidateRetentionIntervals
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.domains.candidates.talent_pool_consent import (
    CandidateTalentPoolCaptureMethod,
    CandidateTalentPoolConsentEventType,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_retention import (
    activate_candidate_retention_policy,
    create_candidate_retention_policy,
    preview_candidate_retention,
)
from app.services.candidate_retention_errors import (
    CandidateRetentionAccessDeniedError,
    CandidateRetentionPolicyNotFoundError,
)
from app.services.candidates import CreateCandidateCommand, create_candidate


def _context(tenant_id: UUID, roles: frozenset[Role]) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject="retention-admin",
        roles=roles,
        request_id="retention-test-request",
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


async def _create_candidate(
    session: AsyncSession,
    tenant_id: UUID,
    suffix: str,
) -> Candidate:
    return await create_candidate(
        session,
        context=_context(tenant_id, frozenset({Role.RECRUITER})),
        command=CreateCandidateCommand(
            full_name=f"Candidate {suffix}",
            email=f"candidate-{suffix}@example.com",
            phone=None,
            location=None,
            source="careers_page",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
        ),
    )


async def _create_application(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    requisition_id: UUID,
    status: ApplicationStatus,
    updated_at: datetime,
) -> None:
    session.add(
        Application(
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            requisition_id=requisition_id,
            status=status,
            created_by_subject="retention-test",
            updated_at=updated_at,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_policy_versions_activate_atomically_and_audit_without_candidate_pii(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    context = _context(tenant_id, frozenset({Role.TENANT_ADMIN}))

    first = await create_candidate_retention_policy(session, context=context)
    await activate_candidate_retention_policy(
        session,
        context=context,
        policy_id=first.id,
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    second = await create_candidate_retention_policy(
        session,
        context=context,
        intervals=CandidateRetentionIntervals(unsuccessful_applicant_days=400),
    )
    await activate_candidate_retention_policy(
        session,
        context=context,
        policy_id=second.id,
        now=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert first.policy_version == 1
    assert first.status is CandidateRetentionPolicyStatus.RETIRED
    assert second.policy_version == 2
    assert second.status is CandidateRetentionPolicyStatus.ACTIVE
    assert second.unsuccessful_applicant_days == 400
    events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_type == "candidate_retention_policy",
            )
        )
    )
    assert {event.action for event in events} == {
        "candidate.retention_policy_drafted",
        "candidate.retention_policy_activated",
    }
    assert all(event.details and "email" not in event.details for event in events)


@pytest.mark.asyncio
async def test_policy_management_is_tenant_admin_only(session: AsyncSession) -> None:
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)

    with pytest.raises(CandidateRetentionAccessDeniedError):
        await create_candidate_retention_policy(
            session,
            context=_context(tenant_id, frozenset({Role.RECRUITER})),
        )


@pytest.mark.asyncio
async def test_policy_lookup_never_crosses_tenant_boundary(session: AsyncSession) -> None:
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, owner_tenant_id)
    await _create_tenant(session, other_tenant_id)
    policy = await create_candidate_retention_policy(
        session,
        context=_context(owner_tenant_id, frozenset({Role.TENANT_ADMIN})),
    )

    with pytest.raises(CandidateRetentionPolicyNotFoundError):
        await preview_candidate_retention(
            session,
            context=_context(other_tenant_id, frozenset({Role.TENANT_ADMIN})),
            policy_id=policy.id,
        )


@pytest.mark.asyncio
async def test_preview_counts_due_upcoming_active_and_erasure_candidates_only(
    session: AsyncSession,
) -> None:
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    await _create_tenant(session, other_tenant_id)
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Retention test role",
        headcount=1,
        status=RequisitionStatus.CLOSED,
        created_by_subject="retention-test",
    )
    session.add(requisition)
    await session.flush()

    due_candidate = await _create_candidate(session, tenant_id, "due")
    upcoming_candidate = await _create_candidate(session, tenant_id, "upcoming")
    active_candidate = await _create_candidate(session, tenant_id, "active")
    pending_candidate = await _create_candidate(session, tenant_id, "pending")
    held_candidate = await _create_candidate(session, tenant_id, "held")
    pool_due_candidate = await _create_candidate(session, tenant_id, "pool-due")
    pool_upcoming_candidate = await _create_candidate(session, tenant_id, "pool-upcoming")
    other_tenant_candidate = await _create_candidate(session, other_tenant_id, "other")
    now = datetime(2026, 9, 25, tzinfo=UTC)
    await _create_application(
        session,
        tenant_id=tenant_id,
        candidate_id=due_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.REJECTED,
        updated_at=now - timedelta(days=400),
    )
    await _create_application(
        session,
        tenant_id=tenant_id,
        candidate_id=upcoming_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.WITHDRAWN,
        updated_at=now - timedelta(days=300),
    )
    await _create_application(
        session,
        tenant_id=tenant_id,
        candidate_id=active_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.SCREENING,
        updated_at=now - timedelta(days=500),
    )
    await _create_application(
        session,
        tenant_id=tenant_id,
        candidate_id=pending_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.REJECTED,
        updated_at=now - timedelta(days=500),
    )
    pending_candidate.privacy_status = CandidatePrivacyStatus.ERASURE_PENDING
    pending_candidate.erasure_requested_at = now - timedelta(days=1)
    session.add(
        CandidateRetentionHold(
            tenant_id=tenant_id,
            candidate_id=held_candidate.id,
            reason=CandidateRetentionHoldReason.LEGAL_CLAIM,
            created_by_subject="privacy-reviewer",
        )
    )
    session.add_all(
        [
            CandidateTalentPoolConsentEvent(
                tenant_id=tenant_id,
                candidate_id=pool_due_candidate.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                capture_method=CandidateTalentPoolCaptureMethod.SIGNED_FORM,
                notice_version="notice-2026-01",
                recorded_by_subject="privacy-reviewer",
                recorded_at=now - timedelta(days=400),
            ),
            CandidateTalentPoolConsentEvent(
                tenant_id=tenant_id,
                candidate_id=pool_upcoming_candidate.id,
                event_version=1,
                event_type=CandidateTalentPoolConsentEventType.GRANTED,
                capture_method=CandidateTalentPoolCaptureMethod.CANDIDATE_PORTAL,
                notice_version="notice-2026-01",
                recorded_by_subject="candidate-portal",
                recorded_at=now - timedelta(days=30),
            ),
        ]
    )
    await _create_application(
        session,
        tenant_id=tenant_id,
        candidate_id=held_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.REJECTED,
        updated_at=now - timedelta(days=500),
    )
    await _create_application(
        session,
        tenant_id=other_tenant_id,
        candidate_id=other_tenant_candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.REJECTED,
        updated_at=now - timedelta(days=500),
    )
    policy = await create_candidate_retention_policy(
        session,
        context=_context(tenant_id, frozenset({Role.TENANT_ADMIN})),
    )

    result = await preview_candidate_retention(
        session,
        context=_context(tenant_id, frozenset({Role.PEOPLE_OPERATIONS})),
        policy_id=policy.id,
        as_of=now,
    )

    assert result.candidates_scanned == 7
    assert result.due_for_review == 2
    assert result.not_yet_due == 2
    assert result.excluded_active_application == 1
    assert result.excluded_non_active_privacy_state == 1
    assert result.excluded_legal_hold == 1
    assert result.not_evaluable == 0
