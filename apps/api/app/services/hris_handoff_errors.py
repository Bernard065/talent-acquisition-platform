"""Errors for the internal HRIS handoff dispatch workflow."""


class HrisHandoffNotFoundError(LookupError):
    """Raised when a tenant-scoped HRIS handoff does not exist."""


class HrisHandoffVersionConflictError(RuntimeError):
    """Raised when a worker acts on stale handoff state."""


class HrisHandoffValidationError(ValueError):
    """Raised when internal HRIS handoff input is invalid."""
