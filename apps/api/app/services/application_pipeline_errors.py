"""Exceptions raised by application pipeline services."""


class ApplicationPipelineAccessDeniedError(PermissionError):
    """Raised when a caller cannot change an application pipeline stage."""


class ApplicationVersionConflictError(RuntimeError):
    """Raised when a caller transitions a stale application version."""


class ApplicationRejectionReasonError(ValueError):
    """Raised when rejection reason requirements are not satisfied."""
