"""Transactional, tenant-scoped interviewer feedback services."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import User
from app.db.models.interview import InterviewParticipant
from app.db.models.interview_feedback import InterviewFeedback
from app.db.transactions import transactional
from app.domains.interviews.enums import (
    InterviewFeedbackStatus,
    InterviewParticipantRole,
    InterviewRecommendation,
)
from app.services.audit import record_audit_event
from app.services.interview_feedback_errors import (
    InterviewFeedbackAccessDeniedError,
    InterviewFeedbackAlreadyExistsError,
    InterviewFeedbackIncompleteError,
    InterviewFeedbackNotEditableError,
    InterviewFeedbackNotFoundError,
    InterviewFeedbackVersionConflictError,
)

_MAX_FEEDBACK_TEXT_LENGTH = 5_000
_UNIQUE_VIOLATION_SQLSTATE = "23505"


@dataclass(frozen=True, slots=True)
class CreateInterviewFeedbackDraftCommand:
    """Initial optional content for one interviewer's feedback draft."""

    overall_rating: int | None = None
    recommendation: InterviewRecommendation | None = None
    strengths: str | None = None
    concerns: str | None = None

    def __post_init__(self) -> None:
        _validate_rating(self.overall_rating)
        object.__setattr__(
            self,
            "strengths",
            _normalize_optional_text(self.strengths, "strengths"),
        )
        object.__setattr__(
            self,
            "concerns",
            _normalize_optional_text(self.concerns, "concerns"),
        )


@dataclass(frozen=True, slots=True)
class UpdateInterviewFeedbackDraftCommand:
    """Replacement content for one versioned feedback draft."""

    expected_version: int
    overall_rating: int | None = None
    recommendation: InterviewRecommendation | None = None
    strengths: str | None = None
    concerns: str | None = None

    def __post_init__(self) -> None:
        _validate_expected_version(self.expected_version)
        _validate_rating(self.overall_rating)
        object.__setattr__(
            self,
            "strengths",
            _normalize_optional_text(self.strengths, "strengths"),
        )
        object.__setattr__(
            self,
            "concerns",
            _normalize_optional_text(self.concerns, "concerns"),
        )


@dataclass(frozen=True, slots=True)
class SubmitInterviewFeedbackCommand:
    """Final content required to submit an immutable interviewer assessment."""

    expected_version: int
    overall_rating: int
    recommendation: InterviewRecommendation
    strengths: str | None = None
    concerns: str | None = None

    def __post_init__(self) -> None:
        _validate_expected_version(self.expected_version)
        _validate_rating(self.overall_rating)
        object.__setattr__(
            self,
            "strengths",
            _normalize_optional_text(self.strengths, "strengths"),
        )
        object.__setattr__(
            self,
            "concerns",
            _normalize_optional_text(self.concerns, "concerns"),
        )


def _validate_expected_version(expected_version: int) -> None:
    """Require an optimistic-concurrency version."""
    if expected_version < 1:
        raise ValueError("Feedback expected version must be at least 1.")


def _validate_rating(overall_rating: int | None) -> None:
    """Validate the controlled rating range when a rating is supplied."""
    if overall_rating is not None and not 1 <= overall_rating <= 5:
        raise ValueError("Overall rating must be between 1 and 5.")


def _normalize_optional_text(value: str | None, field_name: str) -> str | None:
    """Trim optional feedback text and constrain its persisted size."""
    if value is None:
        return None

    normalized = value.strip()

    if len(normalized) > _MAX_FEEDBACK_TEXT_LENGTH:
        raise ValueError(f"{field_name} must not exceed 5000 characters.")

    return normalized or None


def _require_interviewer_role(context: TenantContext) -> None:
    """Restrict authoring to verified callers with the interviewer role."""
    if Role.INTERVIEWER not in context.roles:
        raise InterviewFeedbackAccessDeniedError(
            "Caller is not permitted to author interview feedback."
        )


async def _get_current_tenant_user_id(
    session: AsyncSession,
    *,
    context: TenantContext,
) -> UUID:
    """Resolve the verified subject to its tenant-owned user record."""
    user_id = await session.scalar(
        select(User.id).where(
            User.tenant_id == context.tenant_id,
            User.external_subject == context.subject,
        )
    )

    if user_id is None:
        raise InterviewFeedbackAccessDeniedError(
            "Caller is not permitted to author interview feedback."
        )

    return user_id


async def _require_assigned_interviewer(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    interviewer_user_id: UUID,
) -> None:
    """Ensure the caller is an interviewer assigned to this tenant session."""
    participant_id = await session.scalar(
        select(InterviewParticipant.id).where(
            InterviewParticipant.tenant_id == context.tenant_id,
            InterviewParticipant.interview_session_id == interview_session_id,
            InterviewParticipant.user_id == interviewer_user_id,
            InterviewParticipant.role == InterviewParticipantRole.INTERVIEWER,
        )
    )

    if participant_id is None:
        raise InterviewFeedbackAccessDeniedError(
            "Caller is not permitted to author feedback for this interview."
        )


def _apply_feedback_content(
    feedback: InterviewFeedback,
    *,
    overall_rating: int | None,
    recommendation: InterviewRecommendation | None,
    strengths: str | None,
    concerns: str | None,
) -> None:
    """Replace draft content without recording sensitive text in audit events."""
    feedback.overall_rating = overall_rating
    feedback.recommendation = recommendation
    feedback.strengths = strengths
    feedback.concerns = concerns


def _is_feedback_unique_violation(error: IntegrityError) -> bool:
    """Recognize concurrent attempts to create the same feedback record."""
    return getattr(error.orig, "sqlstate", None) == _UNIQUE_VIOLATION_SQLSTATE


async def create_interview_feedback_draft(
    session: AsyncSession,
    *,
    context: TenantContext,
    interview_session_id: UUID,
    command: CreateInterviewFeedbackDraftCommand,
) -> InterviewFeedback:
    """Create one draft for the verified assigned interviewer."""
    _require_interviewer_role(context)

    try:
        async with transactional(session):
            interviewer_user_id = await _get_current_tenant_user_id(
                session,
                context=context,
            )
            await _require_assigned_interviewer(
                session,
                context=context,
                interview_session_id=interview_session_id,
                interviewer_user_id=interviewer_user_id,
            )

            feedback = InterviewFeedback(
                tenant_id=context.tenant_id,
                interview_session_id=interview_session_id,
                interviewer_user_id=interviewer_user_id,
                status=InterviewFeedbackStatus.DRAFT,
                overall_rating=command.overall_rating,
                recommendation=command.recommendation,
                strengths=command.strengths,
                concerns=command.concerns,
            )
            session.add(feedback)
            await session.flush()

            record_audit_event(
                session,
                context=context,
                action="interview_feedback.draft_created",
                entity_type="interview_feedback",
                entity_id=str(feedback.id),
                details={
                    "interview_session_id": str(interview_session_id),
                    "status": feedback.status.value,
                    "version": feedback.version,
                },
            )
            await session.flush()
            await session.refresh(feedback)

    except IntegrityError as error:
        if _is_feedback_unique_violation(error):
            raise InterviewFeedbackAlreadyExistsError(
                "Feedback already exists for this interview."
            ) from error
        raise

    return feedback


async def _get_owned_feedback_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    feedback_id: UUID,
) -> InterviewFeedback:
    """Load feedback owned by the verified interviewer and lock its row."""
    interviewer_user_id = await _get_current_tenant_user_id(
        session,
        context=context,
    )

    feedback = await session.scalar(
        select(InterviewFeedback)
        .where(
            InterviewFeedback.id == feedback_id,
            InterviewFeedback.tenant_id == context.tenant_id,
            InterviewFeedback.interviewer_user_id == interviewer_user_id,
        )
        .with_for_update()
    )

    if feedback is None:
        raise InterviewFeedbackNotFoundError("Interview feedback was not found.")

    return feedback


def _require_editable_draft(feedback: InterviewFeedback) -> None:
    """Reject edits to submitted feedback before modifying any fields."""
    if feedback.status is not InterviewFeedbackStatus.DRAFT:
        raise InterviewFeedbackNotEditableError(
            "Submitted interview feedback cannot be changed."
        )


def _require_expected_version(
    feedback: InterviewFeedback,
    expected_version: int,
) -> None:
    """Require a caller to act on the version they last read."""
    if feedback.version != expected_version:
        raise InterviewFeedbackVersionConflictError(
            "Interview feedback has changed since the supplied version."
        )


async def update_interview_feedback_draft(
    session: AsyncSession,
    *,
    context: TenantContext,
    feedback_id: UUID,
    command: UpdateInterviewFeedbackDraftCommand,
) -> InterviewFeedback:
    """Replace a draft's content with optimistic concurrency protection."""
    _require_interviewer_role(context)

    async with transactional(session):
        feedback = await _get_owned_feedback_for_update(
            session,
            context=context,
            feedback_id=feedback_id,
        )
        _require_editable_draft(feedback)
        _require_expected_version(feedback, command.expected_version)

        _apply_feedback_content(
            feedback,
            overall_rating=command.overall_rating,
            recommendation=command.recommendation,
            strengths=command.strengths,
            concerns=command.concerns,
        )
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="interview_feedback.draft_updated",
            entity_type="interview_feedback",
            entity_id=str(feedback.id),
            details={
                "interview_session_id": str(feedback.interview_session_id),
                "status": feedback.status.value,
                "version": feedback.version,
            },
        )
        await session.flush()
        await session.refresh(feedback)

    return feedback


async def submit_interview_feedback(
    session: AsyncSession,
    *,
    context: TenantContext,
    feedback_id: UUID,
    command: SubmitInterviewFeedbackCommand,
) -> InterviewFeedback:
    """Submit one complete assessment and make it immutable."""
    _require_interviewer_role(context)

    async with transactional(session):
        feedback = await _get_owned_feedback_for_update(
            session,
            context=context,
            feedback_id=feedback_id,
        )
        _require_editable_draft(feedback)
        _require_expected_version(feedback, command.expected_version)

        _apply_feedback_content(
            feedback,
            overall_rating=command.overall_rating,
            recommendation=command.recommendation,
            strengths=command.strengths,
            concerns=command.concerns,
        )

        if (
            feedback.overall_rating is None
            or feedback.recommendation is None
        ):
            raise InterviewFeedbackIncompleteError(
                "Overall rating and recommendation are required to submit feedback."
            )

        feedback.status = InterviewFeedbackStatus.SUBMITTED
        feedback.submitted_at = datetime.now(UTC)
        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="interview_feedback.submitted",
            entity_type="interview_feedback",
            entity_id=str(feedback.id),
            details={
                "interview_session_id": str(feedback.interview_session_id),
                "status": feedback.status.value,
                "version": feedback.version,
            },
        )
        await session.flush()
        await session.refresh(feedback)

    return feedback
