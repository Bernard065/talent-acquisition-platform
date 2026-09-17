"""Unit tests for signed outbound webhook HTTP delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.db.models.webhook import WebhookEndpoint, WebhookEvent
from app.infrastructure.webhooks import SignedWebhookDeliveryAdapter
from app.services.webhook_delivery_errors import WebhookDeliveryTransportError


@dataclass
class _FakeWebhookSecretVault:
    """In-memory signing-secret vault for HTTP adapter tests."""

    secret: SecretStr = SecretStr("test-webhook-signing-secret")

    async def store_webhook_signing_secret(self, *, secret: SecretStr) -> str:
        """Persist a test secret in memory and return a synthetic reference."""
        del secret
        return "tap-webhook-" + "a" * 32

    async def resolve_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> SecretStr:
        """Return the in-memory signing secret for a known test reference."""
        assert secret_reference.startswith("tap-webhook-")
        return self.secret

    async def delete_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> None:
        """Record a delete call without affecting the in-memory test state."""
        del secret_reference


async def _public_resolver(_: str) -> tuple[str, ...]:
    """Resolve test destinations to a globally routable public IP."""
    return ("8.8.8.8",)


async def _private_resolver(_: str) -> tuple[str, ...]:
    """Resolve test destinations to a prohibited private address."""
    return ("127.0.0.1",)


def _endpoint() -> WebhookEndpoint:
    """Build one active endpoint without requiring database persistence."""
    return WebhookEndpoint(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Partner HRIS",
        url="https://hooks.partner.example.test/tap",
        credential_reference="tap-webhook-" + "b" * 32,
        created_by_subject="tenant-admin-subject",
    )


def _event(tenant_id: object) -> WebhookEvent:
    """Build one immutable privacy-safe webhook event."""
    return WebhookEvent(
        id=uuid4(),
        tenant_id=tenant_id,
        event_type="application.hired",
        aggregate_type="application",
        aggregate_id=str(uuid4()),
        deduplication_key=f"application-hired:{uuid4()}",
        payload={},
        occurred_at=datetime(2026, 9, 17, 12, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_signs_exact_transmitted_event_body() -> None:
    """The receiver can verify the timestamped HMAC over unchanged bytes."""
    endpoint = _endpoint()
    event = _event(endpoint.tenant_id)
    received: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        received["body"] = await request.aread()
        received["headers"] = dict(request.headers)
        return httpx.Response(204)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = SignedWebhookDeliveryAdapter(
            signing_secret_vault=_FakeWebhookSecretVault(),
            allowed_hosts=("hooks.partner.example.test",),
            client=client,
            host_resolver=_public_resolver,
            clock=lambda: datetime(2026, 9, 17, 12, 1, tzinfo=UTC),
        )

        response_status = await adapter.deliver(
            endpoint=endpoint,
            webhook_event=event,
        )

    body = received["body"]
    headers = received["headers"]

    assert isinstance(body, bytes)
    assert isinstance(headers, dict)
    assert response_status == 204

    timestamp = "1789646460"
    expected_digest = hmac.new(
        b"test-webhook-signing-secret",
        timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    assert headers["x-tap-event-id"] == str(event.id)
    assert headers["x-tap-timestamp"] == timestamp
    assert headers["x-tap-signature"] == f"v1={expected_digest}"


@pytest.mark.asyncio
async def test_emits_only_the_approved_privacy_safe_envelope() -> None:
    """Candidate PII, tenant identifiers, secrets, and credentials never appear."""
    endpoint = _endpoint()
    event = _event(endpoint.tenant_id)
    received_body = b""

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal received_body
        received_body = await request.aread()
        return httpx.Response(200)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        adapter = SignedWebhookDeliveryAdapter(
            signing_secret_vault=_FakeWebhookSecretVault(),
            allowed_hosts=("hooks.partner.example.test",),
            client=client,
            host_resolver=_public_resolver,
        )

        await adapter.deliver(endpoint=endpoint, webhook_event=event)

    payload = json.loads(received_body)

    assert payload == {
        "id": str(event.id),
        "type": "application.hired",
        "occurred_at": "2026-09-17T12:00:00Z",
        "data": {
            "object": {
                "type": "application",
                "id": event.aggregate_id,
            }
        },
    }

    rendered = received_body.decode("utf-8")
    for prohibited_value in (
        str(endpoint.tenant_id),
        endpoint.credential_reference,
        "test-webhook-signing-secret",
        "candidate@example.test",
        "Jane Candidate",
    ):
        assert prohibited_value not in rendered


@pytest.mark.asyncio
async def test_rejects_redirect_responses_without_following_them() -> None:
    """A destination cannot redirect delivery to another network location."""
    endpoint = _endpoint()
    event = _event(endpoint.tenant_id)
    request_count = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1/internal"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
    ) as client:
        adapter = SignedWebhookDeliveryAdapter(
            signing_secret_vault=_FakeWebhookSecretVault(),
            allowed_hosts=("hooks.partner.example.test",),
            client=client,
            host_resolver=_public_resolver,
        )

        with pytest.raises(WebhookDeliveryTransportError) as exc_info:
            await adapter.deliver(endpoint=endpoint, webhook_event=event)

    assert exc_info.value.code == "http_rejected"
    assert exc_info.value.retryable is False
    assert request_count == 1


@pytest.mark.asyncio
async def test_rejects_private_dns_resolution_before_network_call() -> None:
    """Delivery is blocked when a previously valid hostname resolves privately."""
    endpoint = _endpoint()
    event = _event(endpoint.tenant_id)
    request_count = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        adapter = SignedWebhookDeliveryAdapter(
            signing_secret_vault=_FakeWebhookSecretVault(),
            allowed_hosts=("hooks.partner.example.test",),
            client=client,
            host_resolver=_private_resolver,
        )

        with pytest.raises(WebhookDeliveryTransportError) as exc_info:
            await adapter.deliver(endpoint=endpoint, webhook_event=event)

    assert exc_info.value.code == "destination_rejected"
    assert exc_info.value.retryable is False
    assert request_count == 0
