"""PostgreSQL integration tests for interview session lifecycle services."""

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
from app.db.models.interview_session_lifecycle import (
    InterviewSessionLifecycleHistory,
)
from app.db.models.outbox import OutboxEvent
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewLifecycleEventType,
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.services.interview_lifecycle import (
    CancelInterviewSessionCommand,
    CompleteInterviewSessionCommand,
    RescheduleInterviewSessionCommand,
    cancel_interview_session,
    complete_interview_session,
    reschedule_interview_session,
)
from app.services.interview_lifecycle_errors import (
    InterviewLifecycleAccessDeniedError,
    InterviewRescheduleConflictError,
    InterviewSessionNotFoundError,
    InterviewSessionVersionConflictError,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> TenantContext:
    """Build a verified caller context for lifecycle service tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id="interview-lifecycle-test-request-id",
    )


async def _create_tenant_and_participant(
    session: AsyncSession,
    tenant_id: UUID,
) -> User:
    """Create the tenant and reusable internal interview participant."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Lifecycle Tenant {tenant_id.hex[:12]}",
            slug=f"lifecycle-{tenant_id.hex[:12]}",
        )
    )
    participant = User(
        tenant_id=tenant_id,
        external_subject=f"participant-{tenant_id.hex[:12]}",
        email=f"participant-{tenant_id.hex[:12]}@example.test",
        display_name="Interview Participant",
    )
    session.add(participant)
    await session.flush()
    return participant


async def _create_scheduled_interview(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    participant: User,
    start_at: datetime,
    end_at: datetime,
) -> InterviewSession:
    """Create one scheduled interview with a reserved interviewer."""
    candidate_id = uuid4()
    requisition_id = uuid4()

    session.add(
        Candidate(
            id=candidate_id,
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{candidate_id.hex[:12]}@example.test",
            normalized_email=f"ada-{candidate_id.hex[:12]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="recruiter-subject",
        )
    )
    session.add(
        Requisition(
            id=requisition_id,
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="recruiter-subject",
        )
    )
    await session.flush()

    application = Application(
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        requisition_id=requisition_id,
        status=ApplicationStatus.INTERVIEW,
        created_by_subject="recruiter-subject",
    )
    session.add(application)
    await session.flush()

    interview_session = InterviewSession(
        tenant_id=tenant_id,
        application_id=application.id,
        scheduled_start_at=start_at,
        scheduled_end_at=end_at,
        status=InterviewSessionStatus.SCHEDULED,
        created_by_subject="recruiter-subject",
    )
    session.add(interview_session)
    await session.flush()

    session.add(
        InterviewParticipant(
            tenant_id=tenant_id,
            interview_session_id=interview_session.id,
            user_id=participant.id,
            role=InterviewParticipantRole.INTERVIEWER,
            scheduled_time_range=Range(start_at, end_at, bounds="[)"),
        )
    )
    await session.commit()

    return interview_session


@pytest.mark.asyncio
async def test_completes_session_and_records_history_and_audit(
    session: AsyncSession,
) -> None:
    """Complete a scheduled session atomically with history and audit data."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )

    completed = await complete_interview_session(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CompleteInterviewSessionCommand(expected_version=1),
    )

    history = await session.scalar(
        select(InterviewSessionLifecycleHistory).where(
            InterviewSessionLifecycleHistory.interview_session_id
            == interview_session.id
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_session.completed",
            AuditEvent.entity_id == str(interview_session.id),
        )
    )

    assert completed.status is InterviewSessionStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.version == 2
    assert history is not None
    assert history.event_type is InterviewLifecycleEventType.COMPLETED
    assert history.from_status is InterviewSessionStatus.SCHEDULED
    assert history.to_status is InterviewSessionStatus.COMPLETED
    assert audit is not None
    assert audit.details == {"version": 2}


@pytest.mark.asyncio
async def test_cancels_session_with_controlled_reason_and_audit(
    session: AsyncSession,
) -> None:
    """Require and persist a controlled cancellation reason."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )

    cancelled = await cancel_interview_session(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CancelInterviewSessionCommand(
            expected_version=1,
            cancellation_reason=InterviewCancellationReason.CANDIDATE_UNAVAILABLE,
        ),
    )

    history = await session.scalar(
        select(InterviewSessionLifecycleHistory).where(
            InterviewSessionLifecycleHistory.interview_session_id
            == interview_session.id
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_session.cancelled",
            AuditEvent.entity_id == str(interview_session.id),
        )
    )

    assert cancelled.status is InterviewSessionStatus.CANCELLED
    assert cancelled.cancelled_at is not None
    assert (
        cancelled.cancellation_reason
        is InterviewCancellationReason.CANDIDATE_UNAVAILABLE
    )
    assert history is not None
    assert history.event_type is InterviewLifecycleEventType.CANCELLED
    assert (
        history.cancellation_reason
        is InterviewCancellationReason.CANDIDATE_UNAVAILABLE
    )
    assert audit is not None
    assert audit.details["cancellation_reason"] == "candidate_unavailable"


@pytest.mark.asyncio
async def test_cancellation_enqueues_one_calendar_cancel_event(
    session: AsyncSession,
) -> None:
    """Cancellation and calendar deletion work commit atomically."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )

    cancelled = await cancel_interview_session(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=CancelInterviewSessionCommand(
            expected_version=1,
            cancellation_reason=InterviewCancellationReason.OTHER,
        ),
    )

    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "interview.calendar_sync_requested",
                OutboxEvent.aggregate_id == str(cancelled.id),
            )
        )
    )

    assert len(events) == 1

    event = events[0]
    assert event.aggregate_type == "interview_session"
    assert event.deduplication_key == (
        f"calendar-sync:{cancelled.id}:{cancelled.version}:cancel"
    )
    assert event.payload == {
        "interview_session_id": str(cancelled.id),
        "operation": "cancel",
        "interview_version": cancelled.version,
    }

    rendered = str(event.payload)
    for prohibited_value in (
        str(participant.id),
        "cancellation_reason",
        "candidate",
        "participant",
        "email",
    ):
        assert prohibited_value not in rendered


@pytest.mark.asyncio
async def test_reschedules_session_and_updates_participant_reservation(
    session: AsyncSession,
) -> None:
    """Move the session and every participant reservation in one transaction."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )
    new_start_at = datetime(2026, 2, 2, 13, 0, tzinfo=UTC)
    new_end_at = datetime(2026, 2, 2, 14, 0, tzinfo=UTC)

    rescheduled = await reschedule_interview_session(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=RescheduleInterviewSessionCommand(
            expected_version=1,
            scheduled_start_at=new_start_at,
            scheduled_end_at=new_end_at,
        ),
    )

    participant_reservation = await session.scalar(
        select(InterviewParticipant).where(
            InterviewParticipant.interview_session_id == interview_session.id
        )
    )
    history = await session.scalar(
        select(InterviewSessionLifecycleHistory).where(
            InterviewSessionLifecycleHistory.interview_session_id
            == interview_session.id
        )
    )

    assert rescheduled.status is InterviewSessionStatus.SCHEDULED
    assert rescheduled.version == 2
    assert rescheduled.scheduled_start_at == new_start_at
    assert participant_reservation is not None
    assert participant_reservation.scheduled_time_range.lower == new_start_at
    assert participant_reservation.scheduled_time_range.upper == new_end_at
    assert history is not None
    assert history.event_type is InterviewLifecycleEventType.RESCHEDULED
    assert history.previous_scheduled_start_at == datetime(
        2026,
        2,
        2,
        9,
        0,
        tzinfo=UTC,
    )
    assert history.scheduled_start_at == new_start_at


@pytest.mark.asyncio
async def test_rescheduling_enqueues_one_calendar_upsert_event(
    session: AsyncSession,
) -> None:
    """Rescheduling and calendar update work commit atomically."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )
    new_start_at = datetime(2026, 2, 2, 13, 0, tzinfo=UTC)
    new_end_at = datetime(2026, 2, 2, 14, 0, tzinfo=UTC)

    rescheduled = await reschedule_interview_session(
        session,
        context=_context(tenant_id),
        interview_session_id=interview_session.id,
        command=RescheduleInterviewSessionCommand(
            expected_version=1,
            scheduled_start_at=new_start_at,
            scheduled_end_at=new_end_at,
        ),
    )

    events = list(
        await session.scalars(
            select(OutboxEvent).where(
                OutboxEvent.tenant_id == tenant_id,
                OutboxEvent.event_type == "interview.calendar_sync_requested",
                OutboxEvent.aggregate_id == str(rescheduled.id),
            )
        )
    )

    assert len(events) == 1

    event = events[0]
    assert event.aggregate_type == "interview_session"
    assert event.deduplication_key == (
        f"calendar-sync:{rescheduled.id}:{rescheduled.version}:upsert"
    )
    assert event.payload == {
        "interview_session_id": str(rescheduled.id),
        "operation": "upsert",
        "interview_version": rescheduled.version,
    }

    rendered = str(event.payload)
    for prohibited_value in (
        str(participant.id),
        "candidate",
        "participant",
        "email",
        "scheduled_start_at",
        "scheduled_end_at",
    ):
        assert prohibited_value not in rendered


@pytest.mark.asyncio
async def test_reschedule_rejects_participant_double_booking(
    session: AsyncSession,
) -> None:
    """Map PostgreSQL's range exclusion constraint to a domain conflict."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)

    first_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )
    second_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 11, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 12, 0, tzinfo=UTC),
    )
    first_session_id = first_session.id
    second_session_id = second_session.id

    with pytest.raises(InterviewRescheduleConflictError):
        await reschedule_interview_session(
            session,
            context=_context(tenant_id),
            interview_session_id=first_session_id,
            command=RescheduleInterviewSessionCommand(
                expected_version=1,
                scheduled_start_at=datetime(2026, 2, 2, 11, 30, tzinfo=UTC),
                scheduled_end_at=datetime(2026, 2, 2, 12, 30, tzinfo=UTC),
            ),
        )

    await session.refresh(first_session)
    second_session_status = await session.scalar(
        select(InterviewSession.status).where(InterviewSession.id == second_session_id)
    )
    assert first_session.scheduled_start_at == datetime(
        2026,
        2,
        2,
        9,
        0,
        tzinfo=UTC,
    )
    assert second_session_status is InterviewSessionStatus.SCHEDULED


@pytest.mark.asyncio
async def test_rejects_stale_version_and_unauthorized_role(
    session: AsyncSession,
) -> None:
    """Require both current version and lifecycle management permission."""
    tenant_id = uuid4()
    participant = await _create_tenant_and_participant(session, tenant_id)
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )
    interview_session_id = interview_session.id

    with pytest.raises(InterviewSessionVersionConflictError):
        await complete_interview_session(
            session,
            context=_context(tenant_id),
            interview_session_id=interview_session_id,
            command=CompleteInterviewSessionCommand(expected_version=2),
        )

    with pytest.raises(InterviewLifecycleAccessDeniedError):
        await complete_interview_session(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            interview_session_id=interview_session_id,
            command=CompleteInterviewSessionCommand(expected_version=1),
        )


@pytest.mark.asyncio
async def test_hides_session_from_another_tenant(
    session: AsyncSession,
) -> None:
    """Do not reveal the existence of another tenant's interview session."""
    owner_tenant_id = uuid4()
    participant = await _create_tenant_and_participant(
        session,
        owner_tenant_id,
    )
    interview_session = await _create_scheduled_interview(
        session,
        tenant_id=owner_tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )

    with pytest.raises(InterviewSessionNotFoundError):
        await cancel_interview_session(
            session,
            context=_context(uuid4()),
            interview_session_id=interview_session.id,
            command=CancelInterviewSessionCommand(
                expected_version=1,
                cancellation_reason=InterviewCancellationReason.OTHER,
            ),
        )
