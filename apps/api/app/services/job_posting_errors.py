"""Errors for tenant-scoped job posting workflow operations."""


class JobPostingNotFoundError(LookupError):
    """Raised when a posting is absent from the caller's tenant."""


class JobPostingAccessDeniedError(PermissionError):
    """Raised when the caller lacks job-posting management permissions."""


class JobPostingVersionConflictError(ValueError):
    """Raised when a posting changed after the caller last read it."""


class JobPostingRequisitionNotOpenError(ValueError):
    """Raised when publication is attempted for a non-open requisition."""


class JobPostingRequisitionNotApprovedError(ValueError):
    """Raised when a posting is requested before requisition approval."""


class JobPostingValidationError(ValueError):
    """Raised when job posting input is structurally invalid."""


class InvalidJobPostingCursorError(ValueError):
    """Raised when job-posting pagination state is malformed."""
