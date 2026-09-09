"""PostgreSQL integration tests for post-interview hiring decisions."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_debrief import (
    ApplicationDebrief,
    ApplicationDecisionHistory,
)
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.interview_feedback import InterviewFeedback
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.decisions.enums import HiringDecision
from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewParticipantRole,
    InterviewRecommendation,
    InterviewSessionStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.hiring_decision_errors import (
    HiringDecisionAccessDeniedError,
    HiringDecisionFeedbackRequiredError,
    HiringDecisionSelfDecisionError,
    HiringDecisionValidationError,
    HiringDecisionVersionConflictError,
)
from app.services.hiring_decisions import (
    RecordHiringDecisionCommand,
    record_hiring_decision,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "decision-subject",
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified decision-maker context."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="hiring-decision-test-request-id",
    )


def _advance_command(
    *,
    expected_application_version: int = 1,
) -> RecordHiringDecisionCommand:
    """Build a valid offer-advancement decision."""
    return RecordHiringDecisionCommand(
        decision=HiringDecision.ADVANCE_TO_OFFER,
        expected_application_version=expected_application_version,
        rationale="The panel agreed that the candidate meets the role requirements.",
    )


async def _seed_decision_data(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    include_submitted_feedback: bool = True,
    decision_maker_participates: bool = False,
) -> Application:
    """Create an interview-stage application and optional submitted feedback."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Decision Tenant {tenant_id.hex[:12]}",
            slug=f"decision-{tenant_id.hex[:12]}",
        )
    )
    await session.flush()

    decision_maker = User(
        tenant_id=tenant_id,
        external_subject="decision-subject",
        email=f"decision-{tenant_id.hex[:12]}@example.test",
        display_name="Decision Maker",
    )
    interviewer = (
        decision_maker
        if decision_maker_participates
        else User(
            tenant_id=tenant_id,
            external_subject="interviewer-subject",
            email=f"interviewer-{tenant_id.hex[:12]}@example.test",
            display_name="Assigned Interviewer",
        )
    )
    session.add(decision_maker)

    if interviewer is not decision_maker:
        session.add(interviewer)

    candidate = Candidate(
        tenant_id=tenant_id,
        full_name="Ada Lovelace",
        email=f"ada-{tenant_id.hex[:12]}@example.test",
        normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
        source="employee_referral",
        source_metadata={},
        consent_status=CandidateConsentStatus.UNKNOWN,
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
        status=ApplicationStatus.INTERVIEW,
        created_by_subject="recruiter-subject",
    )
    session.add(application)
    await session.flush()

    interview_session = InterviewSession(
        tenant_id=tenant_id,
        application_id=application.id,
        scheduled_start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        scheduled_end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
        status=InterviewSessionStatus.COMPLETED,
        completed_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
        created_by_subject="recruiter-subject",
    )
    session.add(interview_session)
    await session.flush()

    session.add(
        InterviewParticipant(
            tenant_id=tenant_id,
            interview_session_id=interview_session.id,
            user_id=interviewer.id,
            role=InterviewParticipantRole.INTERVIEWER,
            scheduled_time_range=Range(
                interview_session.scheduled_start_at,
                interview_session.scheduled_end_at,
                bounds="[)",
            ),
        )
    )

    if include_submitted_feedback:
        session.add(
            InterviewFeedback(
                tenant_id=tenant_id,
                interview_session_id=interview_session.id,
                interviewer_user_id=interviewer.id,
                status=InterviewFeedbackStatus.SUBMITTED,
                overall_rating=5,
                recommendation=InterviewRecommendation.STRONG_YES,
                strengths="Strong technical judgment.",
                concerns=None,
                submitted_at=datetime(2026, 2, 2, 10, 5, tzinfo=UTC),
            )
        )

    await session.commit()
    return application


@pytest.mark.asyncio
async def test_advances_application_to_offer_with_history_and_safe_audit(
    session: AsyncSession,
) -> None:
    """Persist all decision effects together without exposing rationale."""
    tenant_id = uuid4()
    application = await _seed_decision_data(session, tenant_id=tenant_id)

    debrief = await record_hiring_decision(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        command=_advance_command(),
    )

    stored_application = await session.get(Application, application.id)
    decision_history = await session.scalar(
        select(ApplicationDecisionHistory).where(
            ApplicationDecisionHistory.application_debrief_id == debrief.id
        )
    )
    stage_history = await session.scalar(
        select(ApplicationStageHistory).where(
            ApplicationStageHistory.application_id == application.id,
            ApplicationStageHistory.to_status == ApplicationStatus.OFFER,
        )
    )
    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "application.hiring_decision_recorded",
            AuditEvent.entity_id == str(debrief.id),
        )
    )

    assert debrief.decision is HiringDecision.ADVANCE_TO_OFFER
    assert stored_application is not None
    assert stored_application.status is ApplicationStatus.OFFER
    assert stored_application.version == 2

    assert decision_history is not None
    assert decision_history.decision is HiringDecision.ADVANCE_TO_OFFER

    assert stage_history is not None
    assert stage_history.from_status is ApplicationStatus.INTERVIEW
    assert stage_history.to_status is ApplicationStatus.OFFER

    assert audit_event is not None
    assert audit_event.details["decision"] == "advance_to_offer"
    assert audit_event.details["application_version"] == 2
    assert "rationale" not in audit_event.details
    assert "strengths" not in audit_event.details
    assert "concerns" not in audit_event.details


@pytest.mark.asyncio
async def test_reject_decision_requires_and_persists_controlled_reason(
    session: AsyncSession,
) -> None:
    """Transition an interview-stage application to rejected with a reason."""
    tenant_id = uuid4()
    application = await _seed_decision_data(session, tenant_id=tenant_id)

    debrief = await record_hiring_decision(
        session,
        context=_context(tenant_id),
        application_id=application.id,
        command=RecordHiringDecisionCommand(
            decision=HiringDecision.REJECT,
            expected_application_version=1,
            rationale="The panel identified a material gap in the required experience.",
            rejection_reason=ApplicationRejectionReason.FAILED_ASSESSMENT,
        ),
    )

    stored_application = await session.get(Application, application.id)

    assert debrief.decision is HiringDecision.REJECT
    assert (
        debrief.rejection_reason
        is ApplicationRejectionReason.FAILED_ASSESSMENT
    )
    assert stored_application is not None
    assert stored_application.status is ApplicationStatus.REJECTED


@pytest.mark.asyncio
async def test_requires_submitted_feedback_before_decision(
    session: AsyncSession,
) -> None:
    """Do not permit a decision without any submitted panel feedback."""
    tenant_id = uuid4()
    application = await _seed_decision_data(
        session,
        tenant_id=tenant_id,
        include_submitted_feedback=False,
    )
    application_id = application.id

    with pytest.raises(HiringDecisionFeedbackRequiredError):
        await record_hiring_decision(
            session,
            context=_context(tenant_id),
            application_id=application_id,
            command=_advance_command(),
        )

    assert (
        await session.scalar(
            select(ApplicationDebrief.id).where(
                ApplicationDebrief.application_id == application_id,
            )
        )
        is None
    )


@pytest.mark.asyncio
async def test_prevents_interviewer_from_deciding_on_their_own_interview(
    session: AsyncSession,
) -> None:
    """Separate evaluation from final decision authority."""
    tenant_id = uuid4()
    application = await _seed_decision_data(
        session,
        tenant_id=tenant_id,
        decision_maker_participates=True,
    )

    with pytest.raises(HiringDecisionSelfDecisionError):
        await record_hiring_decision(
            session,
            context=_context(tenant_id),
            application_id=application.id,
            command=_advance_command(),
        )


@pytest.mark.asyncio
async def test_requires_authorized_role_and_current_application_version(
    session: AsyncSession,
) -> None:
    """Require both decision authority and optimistic concurrency."""
    tenant_id = uuid4()
    application = await _seed_decision_data(session, tenant_id=tenant_id)
    application_id = application.id

    with pytest.raises(HiringDecisionVersionConflictError):
        await record_hiring_decision(
            session,
            context=_context(tenant_id),
            application_id=application_id,
            command=_advance_command(expected_application_version=2),
        )

    with pytest.raises(HiringDecisionAccessDeniedError):
        await record_hiring_decision(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            application_id=application_id,
            command=_advance_command(),
        )


@pytest.mark.asyncio
async def test_hides_application_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Do not disclose applications outside the caller's tenant."""
    owner_tenant_id = uuid4()
    application = await _seed_decision_data(
        session,
        tenant_id=owner_tenant_id,
    )

    with pytest.raises(ApplicationNotFoundError):
        await record_hiring_decision(
            session,
            context=_context(uuid4()),
            application_id=application.id,
            command=_advance_command(),
        )


def test_validates_decision_command_rules() -> None:
    """Require rationale and enforce rejection-reason semantics."""
    with pytest.raises(HiringDecisionValidationError):
        RecordHiringDecisionCommand(
            decision=HiringDecision.ADVANCE_TO_OFFER,
            expected_application_version=1,
            rationale="   ",
        )

    with pytest.raises(HiringDecisionValidationError):
        RecordHiringDecisionCommand(
            decision=HiringDecision.REJECT,
            expected_application_version=1,
            rationale="The panel reached a decision.",
        )

    with pytest.raises(HiringDecisionValidationError):
        RecordHiringDecisionCommand(
            decision=HiringDecision.ADVANCE_TO_OFFER,
            expected_application_version=1,
            rationale="The panel reached a decision.",
            rejection_reason=ApplicationRejectionReason.OTHER,
        )
