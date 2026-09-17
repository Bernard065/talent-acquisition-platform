"""Errors for tenant-scoped webhook endpoint management."""


class WebhookAccessDeniedError(PermissionError):
    """Raised when a caller lacks tenant-admin webhook permissions."""


class WebhookValidationError(ValueError):
    """Raised when endpoint or subscription input is unsafe or invalid."""


class WebhookVersionConflictError(ValueError):
    """Raised when an endpoint changed after the caller last read it."""


class WebhookEndpointNotFoundError(LookupError):
    """Raised when a tenant-owned webhook endpoint cannot be found."""


class WebhookSecretStorageError(RuntimeError):
    """Raised when the signing-secret vault cannot safely complete an action."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
