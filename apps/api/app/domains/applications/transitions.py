"""Pure application pipeline transition rules."""

from app.domains.candidates.enums import ApplicationStatus

_ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: frozenset(
        {
            ApplicationStatus.SCREENING,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.SCREENING: frozenset(
        {
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.OFFER: frozenset(
        {
            ApplicationStatus.HIRED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.WITHDRAWN,
        }
    ),
    ApplicationStatus.HIRED: frozenset(),
    ApplicationStatus.REJECTED: frozenset(),
    ApplicationStatus.WITHDRAWN: frozenset(),
}


class InvalidApplicationTransition(ValueError):
    """Raised when a pipeline stage change is not permitted."""


def validate_application_transition(
    current_status: ApplicationStatus,
    target_status: ApplicationStatus,
) -> None:
    """Reject transitions outside the explicitly supported pipeline."""
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidApplicationTransition(
            f"Cannot transition application from {current_status.value} "
            f"to {target_status.value}."
        )
