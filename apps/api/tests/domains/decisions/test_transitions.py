"""Pure tests for debrief decision rules."""

import pytest

from app.domains.candidates.enums import ApplicationStatus
from app.domains.decisions.transitions import (
    InvalidHiringDecisionTransition,
    validate_debrief_application_status,
)


def test_allows_debrief_for_application_in_interview_stage() -> None:
    """A final decision is valid only at the interview stage."""
    validate_debrief_application_status(ApplicationStatus.INTERVIEW)


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.APPLIED,
        ApplicationStatus.SCREENING,
        ApplicationStatus.OFFER,
        ApplicationStatus.HIRED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.WITHDRAWN,
    ],
)
def test_rejects_debrief_outside_interview_stage(
    status: ApplicationStatus,
) -> None:
    """Prevent decisions before or after the interview stage."""
    with pytest.raises(InvalidHiringDecisionTransition):
        validate_debrief_application_status(status)
