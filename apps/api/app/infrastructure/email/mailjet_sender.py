"""Mailjet Send API v3.1 adapter for notification email delivery."""

from __future__ import annotations

from datetime import timedelta

import httpx
from email_validator import EmailNotValidError, validate_email
from pydantic import SecretStr

from app.services.email_sender import EmailDeliveryError, EmailMessage

_SEND_EMAIL_URL = "https://api.mailjet.com/v3.1/send"


class MailjetEmailSender:
    """Deliver one-recipient plain-text notifications through Mailjet.

    Mailjet's Send API does not provide an idempotency key for this operation.
    Explicit HTTP 429 responses are safe to retry; transport errors and other
    provider failures are treated as terminal because the send outcome may be
    ambiguous and retrying could deliver duplicates.
    """

    idempotency_retry_window: timedelta | None = None

    def __init__(
        self,
        *,
        api_key: SecretStr,
        secret_key: SecretStr,
        from_address: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        if not api_key.get_secret_value() or not secret_key.get_secret_value():
            raise ValueError("Mailjet API credentials must not be empty.")

        try:
            normalized_from = validate_email(
                from_address,
                check_deliverability=False,
            ).normalized
        except EmailNotValidError as error:
            raise ValueError("Mailjet sender address is invalid.") from error

        self._api_key = api_key
        self._secret_key = secret_key
        self._from_address = normalized_from
        self._http_client = http_client

    async def send(self, message: EmailMessage) -> str:
        """Send the message and return Mailjet's opaque provider message ID."""
        try:
            response = await self._http_client.post(
                _SEND_EMAIL_URL,
                auth=(
                    self._api_key.get_secret_value(),
                    self._secret_key.get_secret_value(),
                ),
                json={
                    "Messages": [
                        {
                            "From": {"Email": self._from_address},
                            "To": [{"Email": message.recipient_email}],
                            "Subject": message.subject,
                            "TextPart": message.text_body,
                        }
                    ]
                },
            )
        except httpx.TransportError:
            raise EmailDeliveryError(
                "mailjet_transport_outcome_unknown",
                retryable=False,
            ) from None

        if not 200 <= response.status_code < 300:
            status_code = response.status_code
            raise EmailDeliveryError(
                "mailjet_rate_limited"
                if status_code == 429
                else "mailjet_provider_rejected",
                retryable=status_code == 429,
            )

        try:
            payload = response.json()
        except ValueError:
            payload = None

        message_id = _successful_message_id(payload)
        if message_id is None:
            raise EmailDeliveryError(
                "mailjet_success_response_invalid",
                retryable=False,
            )

        return message_id


def _successful_message_id(payload: object) -> str | None:
    """Accept only a successful single-recipient response with a bounded ID."""
    if not isinstance(payload, dict):
        return None

    messages = payload.get("Messages")
    if not isinstance(messages, list) or len(messages) != 1:
        return None

    message_result = messages[0]
    if not isinstance(message_result, dict) or message_result.get("Status") != "success":
        return None

    recipients = message_result.get("To")
    if not isinstance(recipients, list) or len(recipients) != 1:
        return None

    recipient_result = recipients[0]
    if not isinstance(recipient_result, dict):
        return None

    message_uuid = recipient_result.get("MessageUUID")
    if isinstance(message_uuid, (str, int)):
        normalized_id = str(message_uuid).strip()
        if normalized_id and len(normalized_id) <= 255:
            return normalized_id

    return None
