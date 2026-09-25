"""PostgreSQL coverage for candidate-level retention review evidence."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
    CandidatePrivacyStatus,
)
from app.domains.candidates.retention_hold_enums import CandidateRetentionHoldReason
from app.domains.candidates.retention_review import CandidateRetentionReviewChecklist
from app.domains.candidates.retention_review_enums import (
    CandidateRetentionReviewDisposition,
    CandidateRetentionReviewPurpose,
    CandidateRetentionReviewReason,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_retention import (
    activate_candidate_retention_policy,
    create_candidate_retention_policy,
)
from app.services.candidate_retention_errors import CandidateRetentionPolicyNotFoundError
from app.services.candidate_retention_holds import place_candidate_retention_hold
from app.services.candidate_retention_review_errors import (
    CandidateRetentionReviewAccessDeniedError,
    CandidateRetentionReviewNotFoundError,
    CandidateRetentionReviewStateError,
)
from app.services.candidate_retention_reviews import (
    RecordCandidateRetentionReviewCommand,
    record_candidate_retention_review,
)
from app.services.candidates import CreateCandidateCommand, create_candidate


def _context(
    tenant_id: UUID,
    roles: frozenset[Role] = frozenset({Role.TENANT_ADMIN}),
    *,
    subject: str = "retention-reviewer-private-subject",
) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="retention-review-test-request",
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
    suffix = uuid4().hex
    return await create_candidate(
        session,
        context=_context(tenant_id, frozenset({Role.RECRUITER})),
        command=CreateCandidateCommand(
            full_name="Retention Review Private Candidate",
            email=f"retention-{suffix}@example.com",
            phone=None,
            location=None,
            source="careers_page",
            source_metadata={"private_marker": "must-not-enter-audit"},
            consent_status=CandidateConsentStatus.UNKNOWN,
        ),
    )


async def _active_policy(
    session: AsyncSession,
    tenant_id: UUID,
) -> CandidateRetentionPolicy:
    context = _context(tenant_id)
    policy = await create_candidate_retention_policy(session, context=context)
    return await activate_candidate_retention_policy(
        session,
        context=context,
        policy_id=policy.id,
        now=datetime(2026, 9, 1, tzinfo=UTC),
    )


def _checklist(*, complete: bool = True) -> CandidateRetentionReviewChecklist:
    return CandidateRetentionReviewChecklist(
        active_matters_reviewed=complete,
        legal_holds_reviewed=complete,
        other_lawful_basis_reviewed=complete,
        employee_obligations_reviewed=complete,
        external_processors_reviewed=complete,
        backup_restore_safeguards_reviewed=complete,
    )


def _command(
    policy_id: UUID,
    *,
    disposition: CandidateRetentionReviewDisposition = (CandidateRetentionReviewDisposition.RETAIN),
    reason: CandidateRetentionReviewReason = (CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS),
    next_review_at: datetime | None = datetime(2027, 9, 1, tzinfo=UTC),
    checklist: CandidateRetentionReviewChecklist | None = None,
) -> RecordCandidateRetentionReviewCommand:
    return RecordCandidateRetentionReviewCommand(
        policy_id=policy_id,
        purpose=CandidateRetentionReviewPurpose.UNSUCCESSFUL_APPLICANT,
        disposition=disposition,
        reason_code=reason,
        checklist=checklist or _checklist(),
        next_review_at=next_review_at,
    )


async def _add_application(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    candidate_id: UUID,
    status: ApplicationStatus,
) -> Application:
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Retention test requisition",
        headcount=1,
        status=RequisitionStatus.CLOSED,
        created_by_subject="retention-review-test",
    )
    session.add(requisition)
    await session.flush()
    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        requisition_id=requisition.id,
        status=status,
        created_by_subject="retention-review-test",
    )
    session.add(application)
    await session.flush()
    return application


@pytest.mark.asyncio
async def test_review_snapshots_active_policy_and_records_privacy_safe_audit_atomically(
    session: AsyncSession,
) -> None:
    """Review creation should snapshot active policy data and keep audit details private."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    policy = await _active_policy(session, tenant_id)
    context = _context(
        tenant_id,
        frozenset({Role.PEOPLE_OPERATIONS}),
        subject="reviewer-subject-private",
    )

    first = await record_candidate_retention_review(
        session,
        context=context,
        candidate_id=candidate.id,
        command=_command(policy.id),
        reviewed_at=datetime(2026, 9, 25, 10, tzinfo=UTC),
    )
    second = await record_candidate_retention_review(
        session,
        context=context,
        candidate_id=candidate.id,
        command=_command(policy.id, disposition=CandidateRetentionReviewDisposition.DEFER),
        reviewed_at=datetime(2026, 9, 25, 11, tzinfo=UTC),
    )
    replacement_policy = await create_candidate_retention_policy(
        session,
        context=_context(tenant_id),
    )
    await activate_candidate_retention_policy(
        session,
        context=_context(tenant_id),
        policy_id=replacement_policy.id,
        now=datetime(2026, 10, 1, tzinfo=UTC),
    )

    assert (first.review_number, second.review_number) == (1, 2)
    assert first.policy_id == policy.id
    assert first.policy_version == policy.policy_version
    assert first.unsuccessful_applicant_days == policy.unsuccessful_applicant_days
    assert first.unsuccessful_applicant_days == 365
    assert first.reviewed_by_subject == context.subject
    assert first.next_review_at == datetime(2027, 9, 1, tzinfo=UTC)
    assert candidate.privacy_status is CandidatePrivacyStatus.ACTIVE

    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "candidate.retention_review_recorded",
                AuditEvent.entity_id.in_((str(first.id), str(second.id))),
            )
        )
    )
    assert len(audit_events) == 2
    expected_details = {
        str(first.id): {
            "review_number": 1,
            "policy_version": policy.policy_version,
            "purpose": CandidateRetentionReviewPurpose.UNSUCCESSFUL_APPLICANT.value,
            "disposition": CandidateRetentionReviewDisposition.RETAIN.value,
            "reason_code": CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS.value,
        },
        str(second.id): {
            "review_number": 2,
            "policy_version": policy.policy_version,
            "purpose": CandidateRetentionReviewPurpose.UNSUCCESSFUL_APPLICANT.value,
            "disposition": CandidateRetentionReviewDisposition.DEFER.value,
            "reason_code": CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS.value,
        },
    }
    assert {event.entity_id: event.details for event in audit_events} == expected_details
    audit_text = str(expected_details)
    assert candidate.full_name not in audit_text
    assert candidate.email not in audit_text
    assert "private_marker" not in audit_text
    assert context.subject not in audit_text
    assert not list(await session.scalars(select(OutboxEvent)))


@pytest.mark.asyncio
async def test_manual_erasure_recommendation_is_evidence_only_and_never_queues_deletion(
    session: AsyncSession,
) -> None:
    """Manual erasure recommendations should not trigger a deletion workflow."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    policy = await _active_policy(session, tenant_id)

    review = await record_candidate_retention_review(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
        command=_command(
            policy.id,
            disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
            reason=CandidateRetentionReviewReason.REVIEW_COMPLETE,
            next_review_at=None,
        ),
        reviewed_at=datetime(2026, 9, 25, tzinfo=UTC),
    )

    await session.refresh(candidate)
    assert review.disposition is CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE
    assert candidate.privacy_status is CandidatePrivacyStatus.ACTIVE
    assert candidate.full_name == "Retention Review Private Candidate"
    assert not list(await session.scalars(select(OutboxEvent)))


@pytest.mark.asyncio
async def test_review_requires_authorized_role_and_hides_cross_tenant_candidate_and_policy(
    session: AsyncSession,
) -> None:
    """Review recording must enforce tenant scoping and authorization checks."""
    tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    await _create_tenant(session, other_tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    tenant_policy = await _active_policy(session, tenant_id)
    other_policy = await _active_policy(session, other_tenant_id)

    with pytest.raises(CandidateRetentionReviewAccessDeniedError):
        await record_candidate_retention_review(
            session,
            context=_context(tenant_id, frozenset({Role.RECRUITER})),
            candidate_id=candidate.id,
            command=_command(tenant_policy.id),
        )
    with pytest.raises(CandidateRetentionReviewNotFoundError):
        await record_candidate_retention_review(
            session,
            context=_context(other_tenant_id),
            candidate_id=candidate.id,
            command=_command(other_policy.id),
        )
    with pytest.raises(CandidateRetentionPolicyNotFoundError):
        await record_candidate_retention_review(
            session,
            context=_context(tenant_id),
            candidate_id=candidate.id,
            command=_command(other_policy.id),
        )

    assert not list(await session.scalars(select(CandidateRetentionReview)))


@pytest.mark.asyncio
async def test_recommendation_is_blocked_by_legal_hold_active_application_or_incomplete_hire(
    session: AsyncSession,
) -> None:
    """Manual erasure cannot be recommended while a legal hold or active hiring state exists."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    policy = await _active_policy(session, tenant_id)
    context = _context(tenant_id)
    held_candidate = await _create_candidate(session, tenant_id)
    active_candidate = await _create_candidate(session, tenant_id)
    hired_candidate = await _create_candidate(session, tenant_id)

    await place_candidate_retention_hold(
        session,
        context=context,
        candidate_id=held_candidate.id,
        reason=CandidateRetentionHoldReason.LEGAL_CLAIM,
    )
    await _add_application(
        session,
        tenant_id=tenant_id,
        candidate_id=active_candidate.id,
        status=ApplicationStatus.INTERVIEW,
    )
    await _add_application(
        session,
        tenant_id=tenant_id,
        candidate_id=hired_candidate.id,
        status=ApplicationStatus.HIRED,
    )
    recommendation = _command(
        policy.id,
        disposition=CandidateRetentionReviewDisposition.RECOMMEND_MANUAL_ERASURE,
        reason=CandidateRetentionReviewReason.REVIEW_COMPLETE,
        next_review_at=None,
    )

    for candidate in (held_candidate, active_candidate, hired_candidate):
        with pytest.raises(CandidateRetentionReviewStateError):
            await record_candidate_retention_review(
                session,
                context=context,
                candidate_id=candidate.id,
                command=recommendation,
            )

    assert not list(await session.scalars(select(CandidateRetentionReview)))
    assert not list(await session.scalars(select(OutboxEvent)))


@pytest.mark.asyncio
async def test_review_rows_reject_direct_updates_and_deletes(session: AsyncSession) -> None:
    """Retention review rows should be protected from direct mutation in the database."""
    tenant_id = uuid4()
    await _create_tenant(session, tenant_id)
    candidate = await _create_candidate(session, tenant_id)
    policy = await _active_policy(session, tenant_id)
    review = await record_candidate_retention_review(
        session,
        context=_context(tenant_id),
        candidate_id=candidate.id,
        command=_command(policy.id),
    )
    review_id = review.id

    await session.execute(
        text(
            """
            CREATE OR REPLACE FUNCTION prevent_candidate_retention_review_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'candidate retention review evidence is immutable';
            END;
            $$
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE OR REPLACE TRIGGER trg_candidate_retention_review_immutable
            BEFORE UPDATE OR DELETE ON candidate_retention_reviews
            FOR EACH ROW EXECUTE FUNCTION prevent_candidate_retention_review_mutation()
            """
        )
    )
    await session.commit()

    with pytest.raises(DBAPIError):
        await session.execute(
            text(
                "UPDATE candidate_retention_reviews SET reason_code = 'legal_hold' "
                "WHERE id = :review_id"
            ),
            {"review_id": review_id},
        )
    await session.rollback()

    with pytest.raises(DBAPIError):
        await session.execute(
            text("DELETE FROM candidate_retention_reviews WHERE id = :review_id"),
            {"review_id": review_id},
        )
    await session.rollback()

    stored = await session.scalar(
        select(CandidateRetentionReview).where(CandidateRetentionReview.id == review_id)
    )
    assert stored is not None
    assert stored.reason_code is CandidateRetentionReviewReason.ONGOING_LAWFUL_BASIS
    await session.execute(
        text("DROP TRIGGER trg_candidate_retention_review_immutable ON candidate_retention_reviews")
    )
    await session.execute(text("DROP FUNCTION prevent_candidate_retention_review_mutation()"))
    await session.commit()
