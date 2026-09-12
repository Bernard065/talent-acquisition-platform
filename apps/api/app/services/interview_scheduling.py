"""Transactional, tenant-safe interview scheduling service."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.transactions import transactional
from app.domains.candidates.enums import ApplicationStatus
from app.domains.interviews.enums import InterviewParticipantRole, InterviewSessionStatus
from app.services.audit import record_audit_event
from app.services.calendar_sync_events import enqueue_interview_calendar_sync
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.interview_scheduling_errors import (
    InterviewApplicationNotReadyError,
    InterviewParticipantsNotFoundError,
    InterviewScheduleConflictError,
    InterviewSchedulingAccessDeniedError,
    InterviewSchedulingValidationError,
)

_INTERVIEW_SCHEDULING_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)

_EXCLUSION_VIOLATION_SQLSTATE = "23P01"


@dataclass(frozen=True, slots=True)
class InterviewParticipantCommand:
    """One tenant-owned participant reserved for an interview."""

    user_id: UUID
    role: InterviewParticipantRole


@dataclass(frozen=True, slots=True)
class ScheduleInterviewCommand:
    """Validated input for scheduling one interview."""

    scheduled_start_at: datetime
    scheduled_end_at: datetime
    participants: tuple[InterviewParticipantCommand, ...]

    def __post_init__(self) -> None:
        start_at = _normalize_utc(self.scheduled_start_at, "scheduled_start_at")
        end_at = _normalize_utc(self.scheduled_end_at, "scheduled_end_at")

        if end_at <= start_at:
            raise InterviewSchedulingValidationError(
                "scheduled_end_at must be later than scheduled_start_at."
            )

        if not self.participants:
            raise InterviewSchedulingValidationError(
                "At least one interview participant is required."
            )

        participant_ids = [participant.user_id for participant in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise InterviewSchedulingValidationError(
                "An interview participant may appear only once."
            )

        if not any(
            participant.role is InterviewParticipantRole.INTERVIEWER
            for participant in self.participants
        ):
            raise InterviewSchedulingValidationError(
                "At least one participant must have the interviewer role."
            )

        object.__setattr__(self, "scheduled_start_at", start_at)
        object.__setattr__(self, "scheduled_end_at", end_at)


def _normalize_utc(value: datetime, field_name: str) -> datetime:
    """Require timezone-aware datetimes and normalize them to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise InterviewSchedulingValidationError(
            f"{field_name} must include a timezone offset."
        )

    return value.astimezone(UTC)


def _require_scheduling_access(context: TenantContext) -> None:
    """Restrict interview scheduling to recruiting operations roles."""
    if context.roles.isdisjoint(_INTERVIEW_SCHEDULING_ROLES):
        raise InterviewSchedulingAccessDeniedError(
            "Caller is not permitted to schedule interviews."
        )


def _is_exclusion_constraint_violation(error: IntegrityError) -> bool:
    """Return whether PostgreSQL rejected an overlapping participant booking."""
    return getattr(error.orig, "sqlstate", None) == _EXCLUSION_VIOLATION_SQLSTATE


async def schedule_interview(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: ScheduleInterviewCommand,
) -> InterviewSession:
    """Schedule an interview atomically and reserve every participant."""

    _require_scheduling_access(context)

    try:
        async with transactional(session):
            application = await session.scalar(
                select(Application)
                .where(
                    Application.id == application_id,
                    Application.tenant_id == context.tenant_id,
                )
                .with_for_update()
            )
            if application is None:
                raise ApplicationNotFoundError("Application was not found.")

            if application.status is not ApplicationStatus.INTERVIEW:
                raise InterviewApplicationNotReadyError(
                    "Interviews can only be scheduled for applications in the interview stage."
                )

            participant_ids = {
                participant.user_id for participant in command.participants
            }
            tenant_user_ids = set(
                (
                    await session.scalars(
                        select(User.id).where(
                            User.tenant_id == context.tenant_id,
                            User.id.in_(participant_ids),
                        ).with_for_update()
                    )
                ).all()
            )

            if tenant_user_ids != participant_ids:
                raise InterviewParticipantsNotFoundError(
                    "One or more interview participants are unavailable."
                )

            interview_session = InterviewSession(
                tenant_id=context.tenant_id,
                application_id=application.id,
                scheduled_start_at=command.scheduled_start_at,
                scheduled_end_at=command.scheduled_end_at,
                status=InterviewSessionStatus.SCHEDULED,
                created_by_subject=context.subject,
            )
            session.add(interview_session)
            await session.flush()

            for participant in command.participants:
                session.add(
                    InterviewParticipant(
                        tenant_id=context.tenant_id,
                        interview_session_id=interview_session.id,
                        user_id=participant.user_id,
                        role=participant.role,
                        scheduled_time_range=Range(
                            command.scheduled_start_at,
                            command.scheduled_end_at,
                            bounds="[)",
                        ),
                    )
                )

            # PostgreSQL's exclusion constraint is the authoritative,
            # concurrency-safe double-booking check.
            await session.flush()

            enqueue_interview_calendar_sync(
                session,
                context=context,
                interview_session=interview_session,
                operation="upsert",
            )

            record_audit_event(
                session,
                context=context,
                action="interview_session.scheduled",
                entity_type="interview_session",
                entity_id=str(interview_session.id),
                details={
                    "application_id": str(application.id),
                    "scheduled_start_at": command.scheduled_start_at.isoformat(),
                    "scheduled_end_at": command.scheduled_end_at.isoformat(),
                    "participant_count": len(command.participants),
                },
            )
            await session.flush()
            await session.refresh(interview_session)

    except IntegrityError as error:
        if _is_exclusion_constraint_violation(error):
            raise InterviewScheduleConflictError(
                "One or more interview participants are already booked."
            ) from error
        raise

    return interview_session
