"""Transactional, tenant-safe post-interview hiring decision workflow."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.application import Application
from app.db.models.application_debrief import (
    ApplicationDebrief,
    ApplicationDecisionHistory,
)
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.interview_feedback import InterviewFeedback
from app.db.transactions import transactional
from app.domains.applications.transitions import validate_application_transition
from app.domains.candidates.enums import (
    ApplicationRejectionReason,
    ApplicationStatus,
)
from app.domains.decisions.enums import HiringDecision
from app.domains.decisions.transitions import validate_debrief_application_status
from app.services.audit import record_audit_event
from app.services.candidate_errors import ApplicationNotFoundError
from app.services.hiring_decision_errors import (
    HiringDecisionAccessDeniedError,
    HiringDecisionAlreadyExistsError,
    HiringDecisionFeedbackRequiredError,
    HiringDecisionSelfDecisionError,
    HiringDecisionValidationError,
    HiringDecisionVersionConflictError,
)

_DECISION_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.PEOPLE_OPERATIONS,
    }
)
_MAX_RATIONALE_LENGTH = 5_000


@dataclass(frozen=True, slots=True)
class RecordHiringDecisionCommand:
    """Validated input for one final post-interview application decision."""

    decision: HiringDecision
    expected_application_version: int
    rationale: str
    rejection_reason: ApplicationRejectionReason | None = None

    def __post_init__(self) -> None:
        if self.expected_application_version < 1:
            raise HiringDecisionValidationError(
                "Application expected version must be at least 1."
            )

        normalized_rationale = self.rationale.strip()

        if not normalized_rationale:
            raise HiringDecisionValidationError("Decision rationale is required.")

        if len(normalized_rationale) > _MAX_RATIONALE_LENGTH:
            raise HiringDecisionValidationError(
                "Decision rationale must not exceed 5000 characters."
            )

        is_rejection = self.decision is HiringDecision.REJECT

        if is_rejection and self.rejection_reason is None:
            raise HiringDecisionValidationError(
                "A rejection reason is required for a reject decision."
            )

        if not is_rejection and self.rejection_reason is not None:
            raise HiringDecisionValidationError(
                "A rejection reason is valid only for a reject decision."
            )

        object.__setattr__(self, "rationale", normalized_rationale)


def _require_decision_access(context: TenantContext) -> None:
    """Restrict final decisions to recruiting operations roles."""
    if context.roles.isdisjoint(_DECISION_WRITE_ROLES):
        raise HiringDecisionAccessDeniedError(
            "Caller is not permitted to record hiring decisions."
        )


def _target_application_status(decision: HiringDecision) -> ApplicationStatus:
    """Map a controlled decision to its application pipeline outcome."""
    if decision is HiringDecision.ADVANCE_TO_OFFER:
        return ApplicationStatus.OFFER

    return ApplicationStatus.REJECTED


async def _has_submitted_feedback(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    application_id: UUID,
) -> bool:
    """Return whether the application has at least one submitted assessment."""
    submitted_feedback_id = await session.scalar(
        select(InterviewFeedback.id)
        .join(
            InterviewSession,
            InterviewSession.id == InterviewFeedback.interview_session_id,
        )
        .where(
            InterviewFeedback.tenant_id == tenant_id,
            InterviewFeedback.status == "submitted",
            InterviewSession.tenant_id == tenant_id,
            InterviewSession.application_id == application_id,
        )
        .limit(1)
    )
    return submitted_feedback_id is not None


async def _caller_participated_in_application_interview(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
) -> bool:
    """Return whether the caller participated in any interview for the application."""
    participant_id = await session.scalar(
        select(InterviewParticipant.id)
        .join(
            InterviewSession,
            InterviewSession.id == InterviewParticipant.interview_session_id,
        )
        .join(User, User.id == InterviewParticipant.user_id)
        .where(
            InterviewParticipant.tenant_id == context.tenant_id,
            InterviewSession.tenant_id == context.tenant_id,
            InterviewSession.application_id == application_id,
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
        .limit(1)
    )
    return participant_id is not None


async def record_hiring_decision(
    session: AsyncSession,
    *,
    context: TenantContext,
    application_id: UUID,
    command: RecordHiringDecisionCommand,
) -> ApplicationDebrief:
    """Record one final decision and transition the application atomically."""
    _require_decision_access(context)

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

        if application.version != command.expected_application_version:
            raise HiringDecisionVersionConflictError(
                "Application has changed since the supplied version."
            )

        validate_debrief_application_status(application.status)

        existing_debrief = await session.scalar(
            select(ApplicationDebrief.id).where(
                ApplicationDebrief.tenant_id == context.tenant_id,
                ApplicationDebrief.application_id == application.id,
            )
        )
        if existing_debrief is not None:
            raise HiringDecisionAlreadyExistsError(
                "A final hiring decision already exists for this application."
            )

        if not await _has_submitted_feedback(
            session,
            tenant_id=context.tenant_id,
            application_id=application.id,
        ):
            raise HiringDecisionFeedbackRequiredError(
                "At least one submitted interview feedback record is required."
            )

        if await _caller_participated_in_application_interview(
            session,
            context=context,
            application_id=application.id,
        ):
            raise HiringDecisionSelfDecisionError(
                "Interview participants cannot decide on their own interviews."
            )

        previous_status = application.status
        target_status = _target_application_status(command.decision)
        validate_application_transition(previous_status, target_status)

        application.status = target_status

        debrief = ApplicationDebrief(
            tenant_id=context.tenant_id,
            application_id=application.id,
            decision=command.decision,
            rationale=command.rationale,
            rejection_reason=command.rejection_reason,
            decided_by_subject=context.subject,
        )
        session.add(debrief)
        await session.flush()

        session.add(
            ApplicationDecisionHistory(
                tenant_id=context.tenant_id,
                application_id=application.id,
                application_debrief_id=debrief.id,
                decision=command.decision,
                rejection_reason=command.rejection_reason,
                decided_by_subject=context.subject,
            )
        )
        session.add(
            ApplicationStageHistory(
                tenant_id=context.tenant_id,
                application_id=application.id,
                from_status=previous_status,
                to_status=target_status,
                rejection_reason=command.rejection_reason,
                transitioned_by_subject=context.subject,
            )
        )
        await session.flush()

        # Do not put the rationale or interviewer feedback text in audit data.
        record_audit_event(
            session,
            context=context,
            action="application.hiring_decision_recorded",
            entity_type="application_debrief",
            entity_id=str(debrief.id),
            details={
                "application_id": str(application.id),
                "decision": command.decision.value,
                "rejection_reason": (
                    command.rejection_reason.value
                    if command.rejection_reason is not None
                    else None
                ),
                "application_version": application.version,
            },
        )
        await session.flush()
        await session.refresh(debrief)

    return debrief
