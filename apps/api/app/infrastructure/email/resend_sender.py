"""Resend adapter for idempotent transactional email delivery."""

from __future__ import annotations

from datetime import timedelta

import httpx
from email_validator import EmailNotValidError, validate_email
from pydantic import SecretStr

from app.services.email_sender import EmailDeliveryError, EmailMessage

_SEND_EMAIL_URL = "https://api.resend.com/emails"
_RESEND_IDEMPOTENCY_RETENTION = timedelta(hours=24)
_IDEMPOTENCY_SAFETY_MARGIN = timedelta(hours=1)
_CONCURRENT_IDEMPOTENCY_ERROR = "concurrent_idempotent_requests"
_IDEMPOTENCY_PAYLOAD_ERROR = "invalid_idempotent_request"


class ResendEmailSender:
    """Send plain-text notifications with stable provider idempotency keys.

    Resend retains idempotency keys for 24 hours. The retry window is
    deliberately one hour shorter so worker recovery cannot unknowingly send
    the same notification after the provider has forgotten its key.
    """

    idempotency_retry_window: timedelta | None = (
        _RESEND_IDEMPOTENCY_RETENTION - _IDEMPOTENCY_SAFETY_MARGIN
    )

    def __init__(
        self,
        *,
        api_key: SecretStr,
        from_address: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        secret_value = api_key.get_secret_value()
        if not secret_value:
            raise ValueError("Resend API key must not be empty.")

        try:
            normalized_from = validate_email(
                from_address,
                check_deliverability=False,
            ).normalized
        except EmailNotValidError as error:
            raise ValueError("Resend sender address is invalid.") from error

        self._api_key = api_key
        self._from_address = normalized_from
        self._http_client = http_client

    async def send(self, message: EmailMessage) -> str:
        """Submit a deterministic payload and return the provider message ID."""
        if not message.idempotency_key or len(message.idempotency_key) > 256:
            raise EmailDeliveryError(
                "resend_idempotency_key_invalid",
                retryable=False,
            )

        try:
            response = await self._http_client.post(
                _SEND_EMAIL_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key.get_secret_value()}",
                    "Idempotency-Key": message.idempotency_key,
                },
                json={
                    "from": self._from_address,
                    "to": [message.recipient_email],
                    "subject": message.subject,
                    "text": message.text_body,
                },
            )
        except httpx.TransportError:
            raise EmailDeliveryError(
                "resend_transport_error",
                retryable=True,
            ) from None

        if not 200 <= response.status_code < 300:
            await self._raise_for_provider_response(response)

        try:
            payload = response.json()
        except ValueError:
            payload = None

        message_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 255:
            raise EmailDeliveryError(
                "resend_success_response_invalid",
                retryable=True,
            )

        return message_id.strip()

    @staticmethod
    async def _raise_for_provider_response(response: httpx.Response) -> None:
        """Map provider errors to stable safe codes without retaining response text."""
        error_code = _provider_error_code(response)
        if response.status_code == 409:
            if error_code == _CONCURRENT_IDEMPOTENCY_ERROR:
                raise EmailDeliveryError(
                    "resend_idempotent_request_in_progress",
                    retryable=True,
                )
            if error_code == _IDEMPOTENCY_PAYLOAD_ERROR:
                raise EmailDeliveryError(
                    "resend_idempotency_payload_conflict",
                    retryable=False,
                )

        status_code = response.status_code
        raise EmailDeliveryError(
            "resend_rate_limited"
            if status_code == 429
            else "resend_provider_unavailable"
            if status_code == 408 or status_code >= 500
            else "resend_request_rejected",
            retryable=status_code == 408 or status_code == 429 or status_code >= 500,
        )


def _provider_error_code(response: httpx.Response) -> str | None:
    """Extract only known machine-readable fields from a JSON error response."""
    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    values: list[object] = [
        payload.get("code"),
        payload.get("name"),
        payload.get("error"),
    ]
    nested_error = payload.get("error")
    if isinstance(nested_error, dict):
        values.extend((nested_error.get("code"), nested_error.get("name")))

    known_codes = {
        _CONCURRENT_IDEMPOTENCY_ERROR,
        _IDEMPOTENCY_PAYLOAD_ERROR,
    }
    for value in values:
        if isinstance(value, str) and value in known_codes:
            return value
    return None
