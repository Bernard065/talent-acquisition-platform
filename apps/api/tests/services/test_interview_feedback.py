"""PostgreSQL integration tests for interviewer feedback services."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewParticipantRole,
    InterviewRecommendation,
    InterviewSessionStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.interview_feedback import (
    CreateInterviewFeedbackDraftCommand,
    SubmitInterviewFeedbackCommand,
    UpdateInterviewFeedbackDraftCommand,
    create_interview_feedback_draft,
    submit_interview_feedback,
    update_interview_feedback_draft,
)
from app.services.interview_feedback_errors import (
    InterviewFeedbackAccessDeniedError,
    InterviewFeedbackNotEditableError,
    InterviewFeedbackVersionConflictError,
)


def _context(
    tenant_id: UUID,
    *,
    subject: str = "interviewer-subject",
    roles: frozenset[Role] = frozenset({Role.INTERVIEWER}),
) -> TenantContext:
    """Build a verified interviewer context for feedback tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles,
        request_id="interview-feedback-test-request-id",
    )


async def _seed_interview(
    session: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[InterviewSession, User, User]:
    """Create one tenant, assigned interviewer, and unassigned tenant user."""
    tenant = Tenant(
        id=tenant_id,
        name=f"Feedback Tenant {tenant_id.hex[:12]}",
        slug=f"feedback-{tenant_id.hex[:12]}",
    )
    session.add(tenant)
    await session.flush()

    interviewer = User(
        tenant_id=tenant_id,
        external_subject="interviewer-subject",
        email=f"interviewer-{tenant_id.hex[:12]}@example.test",
        display_name="Assigned Interviewer",
    )
    unassigned_user = User(
        tenant_id=tenant_id,
        external_subject="unassigned-subject",
        email=f"unassigned-{tenant_id.hex[:12]}@example.test",
        display_name="Unassigned Interviewer",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="recruiter-subject",
    )
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
    session.add_all(
        [
            interviewer,
            unassigned_user,
            requisition,
            candidate,
        ]
    )
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
        completed_at=datetime(2026, 2, 2, 10, 30, tzinfo=UTC),
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
    await session.commit()

    return interview_session, interviewer, unassigned_user


@pytest.mark.asyncio
async def test_assigned_interviewer_creates_draft_and_audits_without_notes(
    session: AsyncSession,
) -> None:
    """Create tenant-owned feedback only for an assigned interviewer."""
    tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=tenant_id,
    )

    feedback = await create_interview_feedback_draft(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CreateInterviewFeedbackDraftCommand(
            strengths="Strong systems design reasoning.",
            concerns="Could offer more concise explanations.",
        ),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_feedback.draft_created",
            AuditEvent.entity_id == str(feedback.id),
        )
    )

    assert feedback.status is InterviewFeedbackStatus.DRAFT
    assert feedback.interviewer_user_id is not None
    assert audit_event is not None
    assert audit_event.details["interview_session_id"] == str(interview_session.id)
    assert "strengths" not in audit_event.details
    assert "concerns" not in audit_event.details


@pytest.mark.asyncio
async def test_rejects_unassigned_interviewer(
    session: AsyncSession,
) -> None:
    """Do not allow a tenant user to write feedback for another panel."""
    tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=tenant_id,
    )

    with pytest.raises(InterviewFeedbackAccessDeniedError):
        await create_interview_feedback_draft(
            session,
            context=_context(
                tenant_id,
                subject="unassigned-subject",
            ),
            interview_session_id=interview_session.id,
            command=CreateInterviewFeedbackDraftCommand(),
        )


@pytest.mark.asyncio
async def test_hides_interview_feedback_workflow_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Do not permit another tenant's interviewer to author feedback."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=owner_tenant_id,
    )
    await _seed_interview(session, tenant_id=other_tenant_id)

    with pytest.raises(InterviewFeedbackAccessDeniedError):
        await create_interview_feedback_draft(
            session,
            context=_context(other_tenant_id),
            interview_session_id=interview_session.id,
            command=CreateInterviewFeedbackDraftCommand(),
        )


@pytest.mark.asyncio
async def test_updates_draft_with_optimistic_concurrency_and_audit_event(
    session: AsyncSession,
) -> None:
    """Update only the version of feedback that the interviewer read."""
    tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=tenant_id,
    )
    draft = await create_interview_feedback_draft(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CreateInterviewFeedbackDraftCommand(),
    )

    updated = await update_interview_feedback_draft(
        session,
        context=_context(tenant_id),
        feedback_id=draft.id,
        command=UpdateInterviewFeedbackDraftCommand(
            expected_version=1,
            overall_rating=4,
            recommendation=InterviewRecommendation.YES,
            strengths="Clear trade-off analysis.",
            concerns=None,
        ),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_feedback.draft_updated",
            AuditEvent.entity_id == str(draft.id),
        )
    )

    assert updated.version == 2
    assert updated.overall_rating == 4
    assert updated.recommendation is InterviewRecommendation.YES
    assert audit_event is not None
    assert audit_event.details["version"] == 2
    assert "strengths" not in audit_event.details


@pytest.mark.asyncio
async def test_rejects_stale_draft_version(
    session: AsyncSession,
) -> None:
    """Require an interviewer to retry after another draft update."""
    tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=tenant_id,
    )
    draft = await create_interview_feedback_draft(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CreateInterviewFeedbackDraftCommand(),
    )

    with pytest.raises(InterviewFeedbackVersionConflictError):
        await update_interview_feedback_draft(
            session,
            context=_context(tenant_id),
            feedback_id=draft.id,
            command=UpdateInterviewFeedbackDraftCommand(
                expected_version=2,
                overall_rating=4,
            ),
        )


@pytest.mark.asyncio
async def test_submits_feedback_and_prevents_service_level_edits(
    session: AsyncSession,
) -> None:
    """Submit a complete assessment and reject all later service edits."""
    tenant_id = uuid4()
    interview_session, _, _ = await _seed_interview(
        session,
        tenant_id=tenant_id,
    )
    draft = await create_interview_feedback_draft(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CreateInterviewFeedbackDraftCommand(),
    )

    submitted = await submit_interview_feedback(
        session,
        context=_context(tenant_id),
        feedback_id=draft.id,
        command=SubmitInterviewFeedbackCommand(
            expected_version=1,
            overall_rating=5,
            recommendation=InterviewRecommendation.STRONG_YES,
            strengths="Excellent technical and communication skills.",
            concerns=None,
        ),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_feedback.submitted",
            AuditEvent.entity_id == str(submitted.id),
        )
    )

    assert submitted.status is InterviewFeedbackStatus.SUBMITTED
    assert submitted.submitted_at is not None
    assert submitted.version == 2
    assert audit_event is not None
    assert "strengths" not in audit_event.details
    assert "concerns" not in audit_event.details

    with pytest.raises(InterviewFeedbackNotEditableError):
        await update_interview_feedback_draft(
            session,
            context=_context(tenant_id),
            feedback_id=submitted.id,
            command=UpdateInterviewFeedbackDraftCommand(
                expected_version=2,
                overall_rating=1,
            ),
        )
