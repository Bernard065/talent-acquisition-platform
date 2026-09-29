"""Port for idempotent notification email delivery."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EmailMessage:
    """A rendered internal notification email."""

    notification_id: UUID
    idempotency_key: str
    recipient_email: str
    subject: str
    text_body: str


class EmailDeliveryError(Exception):
    """A classified delivery error safe for worker retry handling."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class EmailSender(Protocol):
    """Email provider contract with idempotent delivery semantics."""

    @property
    def idempotency_retry_window(self) -> timedelta | None:
        """Latest safe retry age, or ``None`` when keys do not expire."""
        ...

    async def send(self, message: EmailMessage) -> str:
        """Deliver once for the supplied idempotency key and return provider ID."""
