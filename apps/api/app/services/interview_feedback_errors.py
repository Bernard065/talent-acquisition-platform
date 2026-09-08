"""Errors raised by interview feedback services."""


class InterviewFeedbackAccessDeniedError(PermissionError):
    """Raised when a caller cannot author interview feedback."""


class InterviewFeedbackNotFoundError(LookupError):
    """Raised when tenant-scoped feedback cannot be found."""


class InterviewFeedbackAlreadyExistsError(ValueError):
    """Raised when an interviewer already has feedback for a session."""


class InterviewFeedbackNotEditableError(ValueError):
    """Raised when submitted feedback is changed through the service."""


class InterviewFeedbackVersionConflictError(ValueError):
    """Raised when a draft changed since the caller last read it."""


class InterviewFeedbackIncompleteError(ValueError):
    """Raised when feedback lacks required submission fields."""
