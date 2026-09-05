"""Exceptions raised by candidate and application services."""


class CandidateAccessDeniedError(PermissionError):
    """Raised when a caller lacks access to candidate data."""


class CandidateNotFoundError(LookupError):
    """Raised when a candidate is absent from the caller's tenant."""


class CandidateAlreadyExistsError(ValueError):
    """Raised when a tenant already has a candidate with the supplied email."""


class ApplicationNotFoundError(LookupError):
    """Raised when an application is absent from the caller's tenant."""


class ApplicationAlreadyExistsError(ValueError):
    """Raised when a candidate already applied to a requisition."""


class RequisitionNotAcceptingApplicationsError(ValueError):
    """Raised when a requisition is not open for new applications."""
