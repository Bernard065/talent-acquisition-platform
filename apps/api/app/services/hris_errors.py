"""Errors for tenant-scoped HRIS connection and handoff services."""


class HrisAccessDeniedError(PermissionError):
    """Raised when the caller lacks HRIS administration permission."""


class HrisConnectionAlreadyExistsError(ValueError):
    """Raised when a tenant reuses an HRIS provider/name combination."""


class HrisConnectionNotFoundError(LookupError):
    """Raised when a tenant-scoped HRIS connection does not exist."""


class HrisConnectionVersionConflictError(RuntimeError):
    """Raised when a caller attempts a stale HRIS connection mutation."""


class HrisActiveConnectionExistsError(ValueError):
    """Raised when a tenant attempts to configure a second active HRIS target."""


class HrisConnectionValidationError(ValueError):
    """Raised when HRIS connection input is invalid."""


class HrisCredentialStorageError(RuntimeError):
    """Raised when the external HRIS credential vault is unavailable."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
