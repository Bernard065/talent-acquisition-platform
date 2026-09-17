"""Signed HTTP adapter for outbound webhook delivery."""

from __future__ import annotations

import hmac
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import httpx

from app.db.models.webhook import WebhookEndpoint, WebhookEvent
from app.services.webhook_delivery_errors import WebhookDeliveryTransportError
from app.services.webhook_management import (
    HostResolver,
    resolve_public_host,
    validate_webhook_destination,
)
from app.services.webhook_management_errors import WebhookValidationError
from app.services.webhook_secrets import (
    WebhookSigningSecretVault,
    WebhookSigningSecretVaultError,
)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(UTC)


def _canonical_event_body(webhook_event: WebhookEvent) -> bytes:
    """Serialize the approved public webhook event envelope."""
    payload: dict[str, Any] = {
        "id": str(webhook_event.id),
        "type": webhook_event.event_type,
        "occurred_at": webhook_event.occurred_at.astimezone(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        "data": {
            "object": {
                "type": webhook_event.aggregate_type,
                "id": webhook_event.aggregate_id,
            }
        },
    }

    return json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _signature(*, secret: str, timestamp: str, body: bytes) -> str:
    """Create an HMAC signature over the exact transmitted bytes."""
    signed_payload = timestamp.encode("ascii") + b"." + body
    digest = hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        sha256,
    ).hexdigest()
    return f"v1={digest}"


class SignedWebhookDeliveryAdapter:
    """
    Deliver signed webhook events using a caller-supplied HTTP client.

    Redirects are disabled. Destination validation is repeated immediately
    before dispatch. Production infrastructure should additionally restrict
    worker egress to the configured partner destination network.
    """

    def __init__(
        self,
        *,
        signing_secret_vault: WebhookSigningSecretVault,
        allowed_hosts: Sequence[str],
        client: httpx.AsyncClient | None = None,
        host_resolver: HostResolver = resolve_public_host,
        clock: Callable[[], datetime] = _utc_now,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not 1 <= timeout_seconds <= 60:
            raise ValueError("Webhook delivery timeout must be between 1 and 60 seconds.")

        self._signing_secret_vault = signing_secret_vault
        self._allowed_hosts = tuple(allowed_hosts)
        self._host_resolver = host_resolver
        self._clock = clock
        self._timeout = httpx.Timeout(timeout_seconds)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            timeout=self._timeout,
        )

    async def aclose(self) -> None:
        """Close the internally owned HTTP client."""
        if self._owns_client:
            await self._client.aclose()

    async def deliver(
        self,
        *,
        endpoint: WebhookEndpoint,
        webhook_event: WebhookEvent,
    ) -> int:
        """Send one signed event and classify its outcome safely."""
        if endpoint.tenant_id != webhook_event.tenant_id:
            raise WebhookDeliveryTransportError(
                "tenant_mismatch",
                retryable=False,
            )

        try:
            await validate_webhook_destination(
                url=endpoint.url,
                allowed_hosts=self._allowed_hosts,
                host_resolver=self._host_resolver,
            )
        except WebhookValidationError as error:
            raise WebhookDeliveryTransportError(
                "destination_rejected",
                retryable=False,
            ) from error

        try:
            secret = await self._signing_secret_vault.resolve_webhook_signing_secret(
                secret_reference=endpoint.credential_reference,
            )
        except WebhookSigningSecretVaultError as error:
            raise WebhookDeliveryTransportError(
                error.code,
                retryable=error.retryable,
            ) from error

        body = _canonical_event_body(webhook_event)
        timestamp = str(int(self._clock().astimezone(UTC).timestamp()))
        signature = _signature(
            secret=secret.get_secret_value(),
            timestamp=timestamp,
            body=body,
        )

        try:
            response = await self._client.post(
                endpoint.url,
                content=body,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "tap-webhook-delivery/1.0",
                    "X-TAP-Event-ID": str(webhook_event.id),
                    "X-TAP-Timestamp": timestamp,
                    "X-TAP-Signature": signature,
                },
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise WebhookDeliveryTransportError(
                "transport_timeout",
                retryable=True,
            ) from error
        except httpx.TransportError as error:
            raise WebhookDeliveryTransportError(
                "transport_error",
                retryable=True,
            ) from error

        if 200 <= response.status_code < 300:
            return response.status_code

        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            raise WebhookDeliveryTransportError(
                "http_retryable",
                retryable=True,
            )

        raise WebhookDeliveryTransportError(
            "http_rejected",
            retryable=False,
        )
