"""Pure unit tests for application pipeline transition rules."""

import pytest

from app.domains.applications.transitions import (
    InvalidApplicationTransition,
    validate_application_transition,
)
from app.domains.candidates.enums import ApplicationStatus


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ApplicationStatus.APPLIED, ApplicationStatus.SCREENING),
        (ApplicationStatus.APPLIED, ApplicationStatus.REJECTED),
        (ApplicationStatus.SCREENING, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER),
        (ApplicationStatus.OFFER, ApplicationStatus.HIRED),
        (ApplicationStatus.OFFER, ApplicationStatus.WITHDRAWN),
    ],
)
def test_allows_supported_pipeline_transitions(
    current: ApplicationStatus,
    target: ApplicationStatus,
) -> None:
    """Allow only explicitly modeled forward or terminal transitions."""
    validate_application_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (ApplicationStatus.APPLIED, ApplicationStatus.OFFER),
        (ApplicationStatus.SCREENING, ApplicationStatus.APPLIED),
        (ApplicationStatus.INTERVIEW, ApplicationStatus.SCREENING),
        (ApplicationStatus.HIRED, ApplicationStatus.INTERVIEW),
        (ApplicationStatus.REJECTED, ApplicationStatus.SCREENING),
        (ApplicationStatus.WITHDRAWN, ApplicationStatus.APPLIED),
    ],
)
def test_rejects_unsupported_pipeline_transitions(
    current: ApplicationStatus,
    target: ApplicationStatus,
) -> None:
    """Prevent skipped, backward, and terminal-state transitions."""
    with pytest.raises(InvalidApplicationTransition):
        validate_application_transition(current, target)
