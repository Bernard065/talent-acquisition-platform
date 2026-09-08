"""Pure tests for interview lifecycle transition rules."""

import pytest

from app.domains.interviews.enums import InterviewSessionStatus
from app.domains.interviews.transitions import (
    InvalidInterviewSessionTransition,
    validate_interview_cancellation,
    validate_interview_completion,
    validate_interview_reschedule,
)


@pytest.mark.parametrize(
    ("validator", "operation"),
    [
        (validate_interview_completion, "complete"),
        (validate_interview_cancellation, "cancel"),
        (validate_interview_reschedule, "reschedule"),
    ],
)
def test_all_lifecycle_operations_allow_scheduled_sessions(
    validator,
    operation: str,
) -> None:
    """Scheduled is the only mutable interview-session lifecycle state."""
    del operation
    validator(InterviewSessionStatus.SCHEDULED)


@pytest.mark.parametrize(
    ("validator", "operation"),
    [
        (validate_interview_completion, "complete"),
        (validate_interview_cancellation, "cancel"),
        (validate_interview_reschedule, "reschedule"),
    ],
)
@pytest.mark.parametrize(
    "status",
    [
        InterviewSessionStatus.COMPLETED,
        InterviewSessionStatus.CANCELLED,
    ],
)
def test_terminal_sessions_reject_all_lifecycle_operations(
    validator,
    operation: str,
    status: InterviewSessionStatus,
) -> None:
    """Completed and cancelled interviews cannot change again."""
    with pytest.raises(
        InvalidInterviewSessionTransition,
        match=operation,
    ):
        validator(status)
