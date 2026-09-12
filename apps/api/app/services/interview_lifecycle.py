"""Transactional, tenant-safe interview session lifecycle services."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.interview_session_lifecycle import (
    InterviewSessionLifecycleHistory,
)
from app.db.transactions import transactional
from app.domains.interviews.enums import (
    InterviewCancellationReason,
    InterviewLifecycleEventType,
    InterviewSessionStatus,
)
from app.domains.interviews.transitions import (
    validate_interview_cancellation,
    validate_interview_completion,
    validate_interview_reschedule,
)
from app.services.audit import record_audit_event
from app.services.calendar_sync_events import enqueue_interview_calendar_sync
from app.services.interview_lifecycle_errors import (
    InterviewLifecycleAccessDeniedError,
    InterviewLifecycleValidationError,
    InterviewRescheduleConflictError,
    InterviewSessionNotFoundError,
    InterviewSessionVersionConflictError,
)

_LIFECYCLE_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_EXCLUSION_VIOLATION_SQLSTATE = "23P01"


@dataclass(frozen=True, slots=True)
class CompleteInterviewSessionCommand:
    """Request to mark one scheduled interview session as completed."""

    expected_version: int

    def __post_init__(self) -> None:
        _validate_expected_version(self.expected_version)


@dataclass(frozen=True, slots=True)
class CancelInterviewSessionCommand:
    """Request to cancel one scheduled interview session."""

    expected_version: int
    cancellation_reason: InterviewCancellationReason

    def __post_init__(self) -> None:
        _validate_expected_version(self.expected_version)

        if self.cancellation_reason is None:
            raise InterviewLifecycleValidationError(
                "A cancellation reason is required."
            )


@dataclass(frozen=True, slots=True)
class RescheduleInterviewSessionCommand:
    """Request to move one scheduled session to a new UTC interval."""

    expected_version: int
    scheduled_start_at: datetime
    scheduled_end_at: datetime

    def __post_init__(self) -> None:
        _validate_expected_version(self.expected_version)

        start_at = _normalize_utc(
            self.scheduled_start_at,
            "scheduled_start_at",
        )
        end_at = _normalize_utc(
            self.scheduled_end_at,
            "scheduled_end_at",
        )

        if end_at <= start_at:
            raise InterviewLifecycleValidationError(
                "scheduled_end_at must be later than scheduled_start_at."
            )

        object.__setattr__(self, "scheduled_start_at", start_at)
        object.__setattr__(self, "scheduled_end_at", end_at)


def _validate_expected_version(expected_version: int) -> None:
    """Require a valid optimistic-concurrency version."""
    if expected_version < 1:
        raise InterviewLifecycleValidationError(
            "Interview expected version must be at least 1."
        )


def _normalize_utc(value: datetime, field_name: str) -> datetime:
    """Require offset-aware timestamps and normalize them to UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise InterviewLifecycleValidationError(
            f"{field_name} must include a timezone offset."
        )

    return value.astimezone(UTC)


def _require_lifecycle_access(context: TenantContext) -> None:
    """Restrict lifecycle actions to recruiting operations roles."""
    if context.roles.isdisjoint(_LIFECYCLE_WRITE_ROLES):
        raise InterviewLifecycleAccessDeniedError(
            "Caller is not permitted to manage interview sessions."
        )


def _require_expected_version(
    interview_session: InterviewSession,
    expected_version: int,
) -> None:
    """Reject commands derived from an outdated interview representation."""
    if interview_session.version != expected_version:
        raise InterviewSessionVersionConflictError(
            "Interview session has changed since the supplied version."
        )


def _is_exclusion_constraint_violation(error: IntegrityError) -> bool:
    """Recognize PostgreSQL participant time-range conflicts."""
    return getattr(error.orig, "sqlstate", None) == _EXCLUSION_VIOLATION_SQLSTATE


async def _get_session_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
) -> InterviewSession:
    """Load and lock one tenant-owned interview session."""
    interview_session = await session.scalar(
        select(InterviewSession)
        .where(
            InterviewSession.id == interview_session_id,
            InterviewSession.tenant_id == context.tenant_id,
        )
        .with_for_update()
    )

    if interview_session is None:
        raise InterviewSessionNotFoundError("Interview session was not found.")

    return interview_session


def _append_lifecycle_history(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session: InterviewSession,
    event_type: InterviewLifecycleEventType,
    from_status: InterviewSessionStatus,
    previous_scheduled_start_at: datetime | None = None,
    previous_scheduled_end_at: datetime | None = None,
    cancellation_reason: InterviewCancellationReason | None = None,
) -> None:
    """Append an immutable lifecycle event in the caller's transaction."""
    session.add(
        InterviewSessionLifecycleHistory(
            tenant_id=context.tenant_id,
            interview_session_id=interview_session.id,
            event_type=event_type,
            from_status=from_status,
            to_status=interview_session.status,
            previous_scheduled_start_at=previous_scheduled_start_at,
            previous_scheduled_end_at=previous_scheduled_end_at,
            scheduled_start_at=interview_session.scheduled_start_at,
            scheduled_end_at=interview_session.scheduled_end_at,
            cancellation_reason=cancellation_reason,
            occurred_by_subject=context.subject,
        )
    )


async def complete_interview_session(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    command: CompleteInterviewSessionCommand,
) -> InterviewSession:
    """Mark a scheduled interview as completed and audit it atomically."""
    _require_lifecycle_access(context)

    async with transactional(session):
        interview_session = await _get_session_for_update(
            session,
            context=context,
            interview_session_id=interview_session_id,
        )
        _require_expected_version(interview_session, command.expected_version)

        previous_status = interview_session.status
        validate_interview_completion(previous_status)

        interview_session.status = InterviewSessionStatus.COMPLETED
        interview_session.completed_at = datetime.now(UTC)
        await session.flush()

        _append_lifecycle_history(
            session,
            context=context,
            interview_session=interview_session,
            event_type=InterviewLifecycleEventType.COMPLETED,
            from_status=previous_status,
        )
        record_audit_event(
            session,
            context=context,
            action="interview_session.completed",
            entity_type="interview_session",
            entity_id=str(interview_session.id),
            details={"version": interview_session.version},
        )
        await session.flush()
        await session.refresh(interview_session)

    return interview_session


async def cancel_interview_session(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    command: CancelInterviewSessionCommand,
) -> InterviewSession:
    """Cancel a scheduled interview with controlled cancellation metadata."""
    _require_lifecycle_access(context)

    async with transactional(session):
        interview_session = await _get_session_for_update(
            session,
            context=context,
            interview_session_id=interview_session_id,
        )
        _require_expected_version(interview_session, command.expected_version)

        previous_status = interview_session.status
        validate_interview_cancellation(previous_status)

        interview_session.status = InterviewSessionStatus.CANCELLED
        interview_session.cancelled_at = datetime.now(UTC)
        interview_session.cancelled_by_subject = context.subject
        interview_session.cancellation_reason = command.cancellation_reason
        await session.flush()

        enqueue_interview_calendar_sync(
            session,
            context=context,
            interview_session=interview_session,
            operation="cancel",
        )

        _append_lifecycle_history(
            session,
            context=context,
            interview_session=interview_session,
            event_type=InterviewLifecycleEventType.CANCELLED,
            from_status=previous_status,
            cancellation_reason=command.cancellation_reason,
        )
        record_audit_event(
            session,
            context=context,
            action="interview_session.cancelled",
            entity_type="interview_session",
            entity_id=str(interview_session.id),
            details={
                "cancellation_reason": command.cancellation_reason.value,
                "version": interview_session.version,
            },
        )
        await session.flush()
        await session.refresh(interview_session)

    return interview_session


async def reschedule_interview_session(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    command: RescheduleInterviewSessionCommand,
) -> InterviewSession:
    """Move a scheduled interview and all participant reservations atomically."""
    _require_lifecycle_access(context)

    try:
        async with transactional(session):
            interview_session = await _get_session_for_update(
                session,
                context=context,
                interview_session_id=interview_session_id,
            )
            _require_expected_version(interview_session, command.expected_version)

            previous_status = interview_session.status
            validate_interview_reschedule(previous_status)

            previous_start_at = interview_session.scheduled_start_at
            previous_end_at = interview_session.scheduled_end_at

            participants = list(
                await session.scalars(
                    select(InterviewParticipant)
                    .where(
                        InterviewParticipant.tenant_id == context.tenant_id,
                        InterviewParticipant.interview_session_id
                        == interview_session.id,
                    )
                    .with_for_update()
                )
            )

            interview_session.scheduled_start_at = command.scheduled_start_at
            interview_session.scheduled_end_at = command.scheduled_end_at

            for participant in participants:
                participant.scheduled_time_range = Range(
                    command.scheduled_start_at,
                    command.scheduled_end_at,
                    bounds="[)",
                )

            await session.flush()

            enqueue_interview_calendar_sync(
                session,
                context=context,
                interview_session=interview_session,
                operation="upsert",
            )

            _append_lifecycle_history(
                session,
                context=context,
                interview_session=interview_session,
                event_type=InterviewLifecycleEventType.RESCHEDULED,
                from_status=previous_status,
                previous_scheduled_start_at=previous_start_at,
                previous_scheduled_end_at=previous_end_at,
            )
            record_audit_event(
                session,
                context=context,
                action="interview_session.rescheduled",
                entity_type="interview_session",
                entity_id=str(interview_session.id),
                details={
                    "previous_scheduled_start_at": previous_start_at.isoformat(),
                    "previous_scheduled_end_at": previous_end_at.isoformat(),
                    "scheduled_start_at": command.scheduled_start_at.isoformat(),
                    "scheduled_end_at": command.scheduled_end_at.isoformat(),
                    "version": interview_session.version,
                },
            )
            await session.flush()
            await session.refresh(interview_session)

    except IntegrityError as error:
        if _is_exclusion_constraint_violation(error):
            raise InterviewRescheduleConflictError(
                "One or more interview participants are already booked."
            ) from error
        raise

    return interview_session
