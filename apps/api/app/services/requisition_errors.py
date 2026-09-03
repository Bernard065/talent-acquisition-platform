"""Shared exceptions for requisition application services."""


class RequisitionNotFoundError(LookupError):
    """Raised when a requisition is absent from the caller's tenant."""


class RequisitionAccessDeniedError(PermissionError):
    """Raised when a caller lacks access to a requisition operation."""


class RequisitionNotEditableError(ValueError):
    """Raised when a requisition is no longer editable."""


class InvalidRequisitionCursorError(ValueError):
    """Raised when a requisition list cursor is malformed."""
