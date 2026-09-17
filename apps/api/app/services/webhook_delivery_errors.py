"""Errors for durable webhook delivery processing."""


class WebhookDeliveryNotFoundError(LookupError):
    """Raised when a webhook delivery no longer exists."""


class WebhookDeliveryLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns a delivery lease."""


class WebhookDeliveryTransportError(RuntimeError):
    """Classified outbound delivery failure without sensitive details."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
