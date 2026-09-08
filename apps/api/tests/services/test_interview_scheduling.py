"""PostgreSQL integration tests for interview scheduling."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewSession
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import InterviewParticipantRole
from app.domains.requisitions.enums import RequisitionStatus
from app.services.interview_scheduling import (
    InterviewParticipantCommand,
    ScheduleInterviewCommand,
    schedule_interview,
)
from app.services.interview_scheduling_errors import (
    InterviewApplicationNotReadyError,
    InterviewParticipantsNotFoundError,
    InterviewScheduleConflictError,
    InterviewSchedulingAccessDeniedError,
    InterviewSchedulingValidationError,
)


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
    request_id: str = "interview-scheduling-test-request-id",
) -> TenantContext:
    """Build a verified caller context for interview scheduling tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=roles,
        request_id=request_id,
    )


def _command(
    participant_id: UUID,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> ScheduleInterviewCommand:
    """Build a valid, UTC-normalized scheduling command."""
    scheduled_start_at = start_at or datetime(2026, 2, 2, 9, 0, tzinfo=UTC)
    scheduled_end_at = end_at or datetime(2026, 2, 2, 10, 0, tzinfo=UTC)

    return ScheduleInterviewCommand(
        scheduled_start_at=scheduled_start_at,
        scheduled_end_at=scheduled_end_at,
        participants=(
            InterviewParticipantCommand(
                user_id=participant_id,
                role=InterviewParticipantRole.INTERVIEWER,
            ),
        ),
    )


async def _seed_interview_data(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    application_status: ApplicationStatus = ApplicationStatus.INTERVIEW,
    application_count: int = 1,
) -> tuple[list[Application], User]:
    """Create one tenant, one interviewer, and interview-ready applications."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Interview Tenant {tenant_id.hex[:12]}",
            slug=f"interview-{tenant_id.hex[:12]}",
        )
    )

    interviewer = User(
        tenant_id=tenant_id,
        external_subject=f"interviewer-{tenant_id.hex[:12]}",
        email=f"interviewer-{tenant_id.hex[:12]}@example.test",
        display_name="Interview Panel Member",
    )
    requisition = Requisition(
        tenant_id=tenant_id,
        title="Senior Backend Engineer",
        headcount=1,
        status=RequisitionStatus.OPEN,
        created_by_subject="recruiter-subject",
    )
    session.add_all([interviewer, requisition])
    await session.flush()

    applications: list[Application] = []

    for index in range(application_count):
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name=f"Candidate {index}",
            email=f"candidate-{tenant_id.hex[:12]}-{index}@example.test",
            normalized_email=f"candidate-{tenant_id.hex[:12]}-{index}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="recruiter-subject",
        )
        session.add(candidate)
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=application_status,
            created_by_subject="recruiter-subject",
        )
        session.add(application)
        applications.append(application)

    await session.commit()

    return applications, interviewer


def test_rejects_naive_datetimes() -> None:
    """Require timezone-aware scheduling input."""
    participant_id = uuid4()

    with pytest.raises(InterviewSchedulingValidationError):
        _command(
            participant_id,
            start_at=datetime(2026, 2, 2, 9, 0),
            end_at=datetime(2026, 2, 2, 10, 0),
        )


def test_normalizes_offsets_to_utc() -> None:
    """Normalize valid offset-aware timestamps to UTC."""
    participant_id = uuid4()
    command = _command(
        participant_id,
        start_at=datetime(2026, 2, 2, 12, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 13, 0, tzinfo=UTC),
    )

    assert command.scheduled_start_at.tzinfo is UTC
    assert command.scheduled_end_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_schedules_interview_and_records_atomic_audit_event(
    session: AsyncSession,
) -> None:
    """Persist the interview, participant reservation, and audit event together."""
    tenant_id = uuid4()
    applications, interviewer = await _seed_interview_data(
        session,
        tenant_id=tenant_id,
    )

    scheduled = await schedule_interview(
        session,
        context=_context(tenant_id),
        application_id=applications[0].id,
        command=_command(interviewer.id),
    )

    audit_event = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "interview_session.scheduled",
            AuditEvent.entity_id == str(scheduled.id),
        )
    )

    assert scheduled.application_id == applications[0].id
    assert audit_event is not None
    assert audit_event.details["application_id"] == str(applications[0].id)
    assert audit_event.details["participant_count"] == 1


@pytest.mark.asyncio
async def test_rejects_application_not_in_interview_stage(
    session: AsyncSession,
) -> None:
    """Only applications in the interview stage may be scheduled."""
    tenant_id = uuid4()
    applications, interviewer = await _seed_interview_data(
        session,
        tenant_id=tenant_id,
        application_status=ApplicationStatus.SCREENING,
    )

    with pytest.raises(InterviewApplicationNotReadyError):
        await schedule_interview(
            session,
            context=_context(tenant_id),
            application_id=applications[0].id,
            command=_command(interviewer.id),
        )


@pytest.mark.asyncio
async def test_rejects_participant_owned_by_another_tenant(
    session: AsyncSession,
) -> None:
    """Do not allow one tenant to schedule another tenant's users."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()

    applications, _ = await _seed_interview_data(
        session,
        tenant_id=owner_tenant_id,
    )
    _, other_tenant_user = await _seed_interview_data(
        session,
        tenant_id=other_tenant_id,
    )

    with pytest.raises(InterviewParticipantsNotFoundError):
        await schedule_interview(
            session,
            context=_context(owner_tenant_id),
            application_id=applications[0].id,
            command=_command(other_tenant_user.id),
        )


@pytest.mark.asyncio
async def test_requires_interview_scheduling_role(
    session: AsyncSession,
) -> None:
    """Reject callers without recruiting-operations access."""
    tenant_id = uuid4()
    applications, interviewer = await _seed_interview_data(
        session,
        tenant_id=tenant_id,
    )

    with pytest.raises(InterviewSchedulingAccessDeniedError):
        await schedule_interview(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.INTERVIEWER}),
            ),
            application_id=applications[0].id,
            command=_command(interviewer.id),
        )

    sessions = list(
        await session.scalars(
            select(InterviewSession).where(InterviewSession.tenant_id == tenant_id)
        )
    )
    assert sessions == []


@pytest.mark.asyncio
async def test_rejects_overlapping_participant_booking_and_keeps_audit_atomic(
    session: AsyncSession,
) -> None:
    """Let PostgreSQL reject overlaps and roll back the failed schedule."""
    tenant_id = uuid4()
    applications, interviewer = await _seed_interview_data(
        session,
        tenant_id=tenant_id,
        application_count=2,
    )

    first_command = _command(interviewer.id)
    await schedule_interview(
        session,
        context=_context(tenant_id),
        application_id=applications[0].id,
        command=first_command,
    )

    with pytest.raises(InterviewScheduleConflictError):
        await schedule_interview(
            session,
            context=_context(tenant_id),
            application_id=applications[1].id,
            command=_command(
                interviewer.id,
                start_at=first_command.scheduled_start_at + timedelta(minutes=30),
                end_at=first_command.scheduled_end_at + timedelta(minutes=30),
            ),
        )

    sessions = list(
        await session.scalars(
            select(InterviewSession).where(InterviewSession.tenant_id == tenant_id)
        )
    )
    audit_events = list(
        await session.scalars(
            select(AuditEvent).where(AuditEvent.action == "interview_session.scheduled")
        )
    )

    assert len(sessions) == 1
    assert len(audit_events) == 1


@pytest.mark.asyncio
async def test_concurrent_scheduling_allows_only_one_overlapping_booking(
    session: AsyncSession,
    database_engine,
) -> None:
    """Prove the database constraint prevents concurrent double-booking."""
    tenant_id = uuid4()
    applications, interviewer = await _seed_interview_data(
        session,
        tenant_id=tenant_id,
        application_count=2,
    )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    command = _command(interviewer.id)

    async with session_factory() as first_session, session_factory() as second_session:
        results = await asyncio.gather(
            schedule_interview(
                first_session,
                context=_context(tenant_id, request_id="concurrent-request-one"),
                application_id=applications[0].id,
                command=command,
            ),
            schedule_interview(
                second_session,
                context=_context(tenant_id, request_id="concurrent-request-two"),
                application_id=applications[1].id,
                command=command,
            ),
            return_exceptions=True,
        )

    successful_schedules = [result for result in results if isinstance(result, InterviewSession)]
    conflicts = [result for result in results if isinstance(result, InterviewScheduleConflictError)]

    assert len(successful_schedules) == 1
    assert len(conflicts) == 1
