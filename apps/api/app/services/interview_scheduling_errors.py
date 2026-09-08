"""Errors raised by interview scheduling services."""


class InterviewSchedulingAccessDeniedError(PermissionError):
    """Raised when the caller cannot schedule interviews."""


class InterviewApplicationNotReadyError(ValueError):
    """Raised when an application is not in the interview stage."""


class InterviewSchedulingValidationError(ValueError):
    """Raised when scheduling input violates business rules."""


class InterviewParticipantsNotFoundError(LookupError):
    """Raised when one or more participants are not tenant-owned users."""


class InterviewScheduleConflictError(ValueError):
    """Raised when a participant is already booked for the requested interval."""
