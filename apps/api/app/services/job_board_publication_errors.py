"""Safe domain errors for external job-board publication requests."""


class JobBoardPublicationAccessDeniedError(PermissionError):
    """Raised when the caller cannot manage external job-board publishing."""


class JobBoardPublicationNotFoundError(LookupError):
    """Raised when a posting or publication is not visible in the tenant."""


class JobBoardPublicationConflictError(RuntimeError):
    """Raised when local posting state prevents the requested remote action."""


class JobBoardPublicationValidationError(ValueError):
    """Raised when a provider key or operation reason is invalid."""
