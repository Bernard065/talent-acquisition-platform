"""Pure business rules for post-interview hiring decisions."""

from app.domains.candidates.enums import ApplicationStatus


class InvalidHiringDecisionTransition(ValueError):
    """Raised when a hiring decision is not valid for an application state."""


def validate_debrief_application_status(
    application_status: ApplicationStatus,
) -> None:
    """Allow a debrief decision only while the application is in interview."""
    if application_status is not ApplicationStatus.INTERVIEW:
        raise InvalidHiringDecisionTransition(
            "A hiring decision requires an application in the interview stage."
        )
