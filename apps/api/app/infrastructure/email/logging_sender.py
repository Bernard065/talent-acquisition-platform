"""Local-only email sender that records safe delivery metadata."""

from datetime import timedelta

import structlog

from app.services.email_sender import EmailMessage

logger = structlog.get_logger()


class LoggingEmailSender:
    """Development adapter; it deliberately does not send real email."""

    idempotency_retry_window: timedelta | None = None

    async def send(self, message: EmailMessage) -> str:
        """Accept a local email without logging PII or rendered content."""
        logger.info(
            "notification_email_accepted",
            notification_id=str(message.notification_id),
            idempotency_key=message.idempotency_key,
        )
        return f"local:{message.idempotency_key}"
