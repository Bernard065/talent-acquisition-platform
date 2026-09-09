"""Errors raised by the hiring-decision workflow."""


class HiringDecisionAccessDeniedError(PermissionError):
    """Raised when a caller cannot record a hiring decision."""


class HiringDecisionAlreadyExistsError(ValueError):
    """Raised when an application already has a final debrief decision."""


class HiringDecisionFeedbackRequiredError(ValueError):
    """Raised when no submitted interview feedback supports a decision."""


class HiringDecisionSelfDecisionError(PermissionError):
    """Raised when an interviewer tries to decide on their own interview."""


class HiringDecisionVersionConflictError(ValueError):
    """Raised when the application changed since the caller last read it."""


class HiringDecisionValidationError(ValueError):
    """Raised when decision input violates a business rule."""
