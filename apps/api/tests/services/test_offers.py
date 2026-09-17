"""PostgreSQL integration tests for the transactional offer workflow."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.approval import ApprovalPolicy, ApprovalPolicyStep
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.offer import Offer, OfferLifecycleHistory
from app.db.models.offer_approval import OfferApprovalDecision
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.approvals.enums import ApprovalDecisionStatus, ApprovalStatus
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
from app.domains.offers.enums import (
    OfferLifecycleEventType,
    OfferPayPeriod,
    OfferStatus,
)
from app.domains.offers.transitions import InvalidOfferTransitionError
from app.domains.requisitions.enums import RequisitionStatus
from app.domains.signatures.enums import OfferSignatureStatus
from app.services.offer_errors import (
    OfferAccessDeniedError,
    OfferAlreadyExistsError,
    OfferApprovalForbiddenError,
    OfferNotFoundError,
    OfferSelfApprovalError,
    OfferValidationError,
    OfferVersionConflictError,
)
from app.services.offers import (
    CreateOfferCommand,
    accept_offer,
    cancel_offer,
    create_offer,
    decide_offer_approval,
    decline_offer,
    expire_offer,
    send_offer,
    submit_offer_for_approval,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "recruiter-subject",
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for offer-service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="offer-service-test-request-id",
    )


def _offer_command() -> CreateOfferCommand:
    """Build a valid future-dated draft offer."""
    return CreateOfferCommand(
        currency="kes",
        base_salary=Decimal("250000.00"),
        bonus_amount=Decimal("20000.00"),
        pay_period=OfferPayPeriod.MONTHLY,
        proposed_start_date=datetime.now(UTC).date() + timedelta(days=30),
        expires_at=datetime.now(UTC) + timedelta(days=14),
        equity_summary="Employee share plan eligibility applies.",
    )


async def _seed_offer_data(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    approver_subjects: tuple[str, ...] = (
        "approver-one-subject",
        "approver-two-subject",
    ),
) -> tuple[Application, dict[str, User]]:
    """Create one offer-stage application and a default approval policy."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Offer Tenant {tenant_id.hex[:12]}",
            slug=f"offer-{tenant_id.hex[:12]}",
        )
    )

    users = {
        "recruiter-subject": User(
            tenant_id=tenant_id,
            external_subject="recruiter-subject",
            email=f"recruiter-{tenant_id.hex[:12]}@example.test",
            display_name="Recruiter",
        )
    }
    users.update(
        {
            subject: User(
                tenant_id=tenant_id,
                external_subject=subject,
                email=f"{subject}-{tenant_id.hex[:8]}@example.test",
                display_name=subject.replace("-", " ").title(),
            )
            for subject in approver_subjects
        }
    )
    session.add_all(users.values())
    await session.flush()

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
        source="employee_referral",
        source_metadata={},
        consent_status=CandidateConsentStatus.GRANTED,
        created_by_subject="recruiter-subject",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="recruiter-subject",
    )
    session.add_all([candidate, requisition])
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        requisition_id=requisition.id,
        status=ApplicationStatus.OFFER,
        created_by_subject="recruiter-subject",
    )
    session.add(application)
    await session.flush()

    policy = ApprovalPolicy(
        tenant_id=tenant_id,
        name="Default offer approval policy",
        is_default=True,
        is_active=True,
    )
    session.add(policy)
    await session.flush()

    session.add_all(
        [
            ApprovalPolicyStep(
                approval_policy_id=policy.id,
                position=position,
                approver_user_id=users[subject].id,
            )
            for position, subject in enumerate(approver_subjects, start=1)
        ]
    )
    await session.commit()

    return application, users


async def _create_draft_offer(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    application_id: UUID,
) -> Offer:
    """Create a draft offer through the application service."""
    return await create_offer(
        session,
        context=_context(tenant_id),
        application_id=application_id,
        command=_offer_command(),
    )


@pytest.mark.asyncio
async def test_creates_submits_approves_sends_and_accepts_offer_atomically(
    session: AsyncSession,
) -> None:
    """Complete the happy path and hire the application exactly once."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(session, tenant_id=tenant_id)

    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )
    assert offer.currency == "KES"
    assert offer.status is OfferStatus.DRAFT
    assert offer.version == 1

    approval = await submit_offer_for_approval(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=1,
    )
    assert approval.status is ApprovalStatus.PENDING
    assert approval.attempt == 1
    assert approval.policy_snapshot["policy_version"] == 1
    assert len(approval.policy_snapshot["steps"]) == 2

    await decide_offer_approval(
        session,
        context=_context(
            tenant_id,
            subject="approver-one-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        expected_offer_version=2,
        decision=ApprovalDecisionStatus.APPROVED,
    )

    approved = await decide_offer_approval(
        session,
        context=_context(
            tenant_id,
            subject="approver-two-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        expected_offer_version=2,
        decision=ApprovalDecisionStatus.APPROVED,
    )
    assert approved.status is ApprovalStatus.APPROVED

    sent = await send_offer(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=3,
    )
    assert sent.status is OfferStatus.SENT
    assert sent.sent_at is not None

    session.add(
        OfferSignatureRequest(
            tenant_id=tenant_id,
            offer_id=offer.id,
            provider="test-provider",
            document_reference="signed-offer-document",
            status=OfferSignatureStatus.SIGNED,
            offer_version=offer.version,
            currency=offer.currency,
            base_salary=offer.base_salary,
            pay_period=offer.pay_period,
            bonus_amount=offer.bonus_amount,
            proposed_start_date=offer.proposed_start_date,
            expires_at=offer.expires_at,
            signed_at=datetime.now(UTC),
            created_by_subject="recruiter-subject",
        )
    )
    await session.flush()

    accepted = await accept_offer(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=4,
    )

    notification_events = list(
        await session.scalars(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type == "notification.requested",
                OutboxEvent.tenant_id == tenant_id,
            )
            .order_by(OutboxEvent.created_at)
        )
    )

    notification_types = {
        event.payload["notification_event_type"]
        for event in notification_events
    }

    assert {
        "offer.approval_requested",
        "offer.approved",
        "offer.sent",
        "offer.accepted",
    }.issubset(notification_types)

    for event in notification_events:
        assert "base_salary" not in event.payload
        assert "bonus_amount" not in event.payload
        assert "equity_summary" not in event.payload
        assert "candidate_email" not in event.payload
        assert "feedback" not in event.payload

    stored_application = await session.get(Application, application.id)
    history = list(
        await session.scalars(
            select(OfferLifecycleHistory)
            .where(OfferLifecycleHistory.offer_id == offer.id)
            .order_by(OfferLifecycleHistory.occurred_at)
        )
    )
    application_history = await session.scalar(
        select(ApplicationStageHistory).where(
            ApplicationStageHistory.application_id == application.id,
            ApplicationStageHistory.to_status == ApplicationStatus.HIRED,
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "offer.accepted",
            AuditEvent.entity_id == str(offer.id),
        )
    )

    assert accepted.status is OfferStatus.ACCEPTED
    assert accepted.accepted_at is not None
    assert accepted.version == 5
    assert stored_application is not None
    assert stored_application.status is ApplicationStatus.HIRED
    assert application_history is not None
    assert audit is not None
    assert "base_salary" not in audit.details
    assert "bonus_amount" not in audit.details
    assert "equity_summary" not in audit.details
    assert [entry.event_type for entry in history] == [
        OfferLifecycleEventType.CREATED,
        OfferLifecycleEventType.SUBMITTED_FOR_APPROVAL,
        OfferLifecycleEventType.APPROVED,
        OfferLifecycleEventType.SENT,
        OfferLifecycleEventType.ACCEPTED,
    ]


@pytest.mark.asyncio
async def test_enforces_ordered_approvals_and_prevents_self_approval(
    session: AsyncSession,
) -> None:
    """Only the configured current approver may make the next decision."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(session, tenant_id=tenant_id)
    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )
    approval = await submit_offer_for_approval(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=1,
    )

    with pytest.raises(OfferApprovalForbiddenError):
        await decide_offer_approval(
            session,
            context=_context(
                tenant_id,
                subject="approver-two-subject",
                roles=frozenset({Role.HIRING_MANAGER}),
            ),
            approval_id=approval.id,
            expected_offer_version=2,
            decision=ApprovalDecisionStatus.APPROVED,
        )

    tenant_id_with_unsafe_policy = uuid4()
    unsafe_application, _ = await _seed_offer_data(
        session,
        tenant_id=tenant_id_with_unsafe_policy,
        approver_subjects=("recruiter-subject",),
    )
    unsafe_offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id_with_unsafe_policy,
        application_id=unsafe_application.id,
    )

    with pytest.raises(OfferSelfApprovalError):
        await submit_offer_for_approval(
            session,
            context=_context(tenant_id_with_unsafe_policy),
            offer_id=unsafe_offer.id,
            expected_offer_version=1,
        )


@pytest.mark.asyncio
async def test_rejected_approval_returns_offer_to_draft_without_auditing_comment(
    session: AsyncSession,
) -> None:
    """Preserve private approver comments outside the security audit record."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(session, tenant_id=tenant_id)
    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )
    approval = await submit_offer_for_approval(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=1,
    )

    rejected = await decide_offer_approval(
        session,
        context=_context(
            tenant_id,
            subject="approver-one-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        expected_offer_version=2,
        decision=ApprovalDecisionStatus.REJECTED,
        comment="Compensation budget is not yet approved.",
    )

    stored_offer = await session.get(Offer, offer.id)
    decision = await session.scalar(
        select(OfferApprovalDecision)
        .where(OfferApprovalDecision.offer_approval_id == approval.id)
        .order_by(OfferApprovalDecision.step_position)
    )
    lifecycle = await session.scalar(
        select(OfferLifecycleHistory).where(
            OfferLifecycleHistory.offer_id == offer.id,
            OfferLifecycleHistory.event_type
            == OfferLifecycleEventType.APPROVAL_REJECTED,
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "offer_approval.rejected",
            AuditEvent.entity_id == str(approval.id),
        )
    )

    assert rejected.status is ApprovalStatus.REJECTED
    assert stored_offer is not None
    assert stored_offer.status is OfferStatus.DRAFT
    assert decision is not None
    assert decision.comment == "Compensation budget is not yet approved."
    assert lifecycle is not None
    assert audit is not None
    assert "comment" not in audit.details


@pytest.mark.asyncio
async def test_prevents_duplicate_active_offers_and_stale_writes(
    session: AsyncSession,
) -> None:
    """Serialize active offers per application and reject outdated versions."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(session, tenant_id=tenant_id)
    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )
    offer_id = offer.id

    with pytest.raises(OfferAlreadyExistsError):
        await _create_draft_offer(
            session,
            tenant_id=tenant_id,
            application_id=application.id,
        )

    with pytest.raises(OfferVersionConflictError):
        await submit_offer_for_approval(
            session,
            context=_context(tenant_id),
            offer_id=offer_id,
            expected_offer_version=2,
        )


@pytest.mark.asyncio
async def test_enforces_offer_authorization_and_tenant_isolation(
    session: AsyncSession,
) -> None:
    """Do not reveal or mutate offers outside the caller's tenant."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(session, tenant_id=tenant_id)

    with pytest.raises(OfferAccessDeniedError):
        await create_offer(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            application_id=application.id,
            command=_offer_command(),
        )

    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )

    with pytest.raises(OfferNotFoundError):
        await cancel_offer(
            session,
            context=_context(uuid4()),
            offer_id=offer.id,
            expected_offer_version=1,
        )


@pytest.mark.asyncio
async def test_declines_expires_and_rejects_terminal_state_changes(
    session: AsyncSession,
) -> None:
    """Exercise non-acceptance lifecycle paths and terminal-state protection."""
    tenant_id = uuid4()
    application, _ = await _seed_offer_data(
        session,
        tenant_id=tenant_id,
        approver_subjects=("approver-one-subject",),
    )
    offer = await _create_draft_offer(
        session,
        tenant_id=tenant_id,
        application_id=application.id,
    )
    approval = await submit_offer_for_approval(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=1,
    )
    await decide_offer_approval(
        session,
        context=_context(
            tenant_id,
            subject="approver-one-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        ),
        approval_id=approval.id,
        expected_offer_version=2,
        decision=ApprovalDecisionStatus.APPROVED,
    )
    sent = await send_offer(
        session,
        context=_context(tenant_id),
        offer_id=offer.id,
        expected_offer_version=3,
    )

    declined = await decline_offer(
        session,
        context=_context(tenant_id),
        offer_id=sent.id,
        expected_offer_version=4,
    )
    assert declined.status is OfferStatus.DECLINED

    with pytest.raises(InvalidOfferTransitionError):
        await cancel_offer(
            session,
            context=_context(tenant_id),
            offer_id=declined.id,
            expected_offer_version=5,
        )

    second_application, _ = await _seed_offer_data(session, tenant_id=uuid4())
    second_offer = await _create_draft_offer(
        session,
        tenant_id=second_application.tenant_id,
        application_id=second_application.id,
    )
    second_offer.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()

    with pytest.raises(OfferValidationError):
        await expire_offer(
            session,
            context=_context(second_application.tenant_id),
            offer_id=second_offer.id,
            expected_offer_version=2,
        )
