"""Pure interview-session lifecycle transition rules."""

from app.domains.interviews.enums import InterviewSessionStatus


class InvalidInterviewSessionTransition(ValueError):
    """Raised when an interview lifecycle operation is not allowed."""


def _require_scheduled(
    current_status: InterviewSessionStatus,
    operation: str,
) -> None:
    """Allow lifecycle operations only for scheduled interview sessions."""
    if current_status is not InterviewSessionStatus.SCHEDULED:
        raise InvalidInterviewSessionTransition(
            f"Interview session cannot be {operation} from {current_status.value}."
        )


def validate_interview_completion(
    current_status: InterviewSessionStatus,
) -> None:
    """Validate the scheduled-to-completed lifecycle transition."""
    _require_scheduled(current_status, "completed")


def validate_interview_cancellation(
    current_status: InterviewSessionStatus,
) -> None:
    """Validate the scheduled-to-cancelled lifecycle transition."""
    _require_scheduled(current_status, "cancelled")


def validate_interview_reschedule(
    current_status: InterviewSessionStatus,
) -> None:
    """Validate an in-place schedule change."""
    _require_scheduled(current_status, "rescheduled")
