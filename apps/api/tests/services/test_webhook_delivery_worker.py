"""PostgreSQL execution tests for the webhook delivery orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.identity import Tenant
from app.db.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
)
from app.domains.webhooks.enums import (
    WebhookDeliveryStatus,
    WebhookEndpointStatus,
)
from app.services.webhook_delivery_errors import WebhookDeliveryTransportError
from app.services.webhook_delivery_worker import (
    WebhookDeliveryProcessResult,
    process_pending_webhook_deliveries,
)


@dataclass
class _FakeDispatcher:
    """Deterministic outbound delivery substitute."""

    response_status_code: int = 202
    error: WebhookDeliveryTransportError | None = None
    delivered_event_ids: list[UUID] = field(default_factory=list)

    async def deliver(
        self,
        *,
        endpoint: WebhookEndpoint,
        webhook_event: WebhookEvent,
    ) -> int:
        """Record delivery or raise the configured classified failure."""
        assert endpoint.tenant_id == webhook_event.tenant_id
        self.delivered_event_ids.append(webhook_event.id)

        if self.error is not None:
            raise self.error

        return self.response_status_code


async def _seed_delivery(
    session: AsyncSession,
    *,
    endpoint_status: WebhookEndpointStatus = WebhookEndpointStatus.ACTIVE,
) -> tuple[UUID, UUID]:
    """Create one tenant-owned delivery ready for worker processing."""
    tenant_id = uuid4()

    session.add(
        Tenant(
            id=tenant_id,
            name=f"Webhook Worker Tenant {tenant_id.hex[:12]}",
            slug=f"webhook-worker-{tenant_id.hex[:12]}",
        )
    )

    endpoint = WebhookEndpoint(
        tenant_id=tenant_id,
        name="Partner HRIS",
        url="https://hooks.partner.example.test/tap",
        credential_reference=f"tap-webhook-{uuid4().hex}",
        status=endpoint_status,
        created_by_subject="tenant-admin-subject",
    )
    session.add(endpoint)
    await session.flush()

    event = WebhookEvent(
        tenant_id=tenant_id,
        event_type="application.hired",
        aggregate_type="application",
        aggregate_id=str(uuid4()),
        deduplication_key=f"application-hired:{uuid4()}",
        payload={},
    )
    session.add(event)
    await session.flush()

    delivery = WebhookDelivery(
        tenant_id=tenant_id,
        webhook_endpoint_id=endpoint.id,
        webhook_event_id=event.id,
        event_type=event.event_type,
    )
    session.add(delivery)
    await session.commit()

    return delivery.id, event.id


@pytest.mark.asyncio
async def test_worker_delivers_successful_event(
    session: AsyncSession,
) -> None:
    """A successful receiver response marks the delivery complete."""
    delivery_id, event_id = await _seed_delivery(session)
    dispatcher = _FakeDispatcher(response_status_code=202)

    result = await process_pending_webhook_deliveries(
        session,
        worker_id="webhook-worker-one",
        dispatcher=dispatcher,
    )

    delivery = await session.get(WebhookDelivery, delivery_id)
    assert delivery is not None

    assert result == WebhookDeliveryProcessResult(
        claimed=1,
        delivered=1,
        retried=0,
        failed=0,
        disabled=0,
    )
    assert dispatcher.delivered_event_ids == [event_id]
    assert delivery.status is WebhookDeliveryStatus.DELIVERED
    assert delivery.response_status_code == 202
    assert delivery.delivered_at is not None
    assert delivery.locked_at is None
    assert delivery.locked_by is None


@pytest.mark.asyncio
async def test_worker_retries_retryable_receiver_failure(
    session: AsyncSession,
) -> None:
    """Temporary transport failures release the delivery for retry."""
    delivery_id, _ = await _seed_delivery(session)
    dispatcher = _FakeDispatcher(
        error=WebhookDeliveryTransportError(
            "transport_timeout",
            retryable=True,
        )
    )

    result = await process_pending_webhook_deliveries(
        session,
        worker_id="webhook-worker-one",
        dispatcher=dispatcher,
    )

    delivery = await session.get(WebhookDelivery, delivery_id)
    assert delivery is not None

    assert result == WebhookDeliveryProcessResult(
        claimed=1,
        delivered=0,
        retried=1,
        failed=0,
        disabled=0,
    )
    assert delivery.status is WebhookDeliveryStatus.PENDING
    assert delivery.attempts == 1
    assert delivery.last_error_code == "transport_timeout"
    assert delivery.locked_at is None
    assert delivery.locked_by is None


@pytest.mark.asyncio
async def test_worker_terminally_fails_rejected_receiver(
    session: AsyncSession,
) -> None:
    """Permanent receiver errors do not remain eligible for retry."""
    delivery_id, _ = await _seed_delivery(session)
    dispatcher = _FakeDispatcher(
        error=WebhookDeliveryTransportError(
            "http_rejected",
            retryable=False,
        )
    )

    result = await process_pending_webhook_deliveries(
        session,
        worker_id="webhook-worker-one",
        dispatcher=dispatcher,
    )

    delivery = await session.get(WebhookDelivery, delivery_id)
    assert delivery is not None

    assert result == WebhookDeliveryProcessResult(
        claimed=1,
        delivered=0,
        retried=0,
        failed=1,
        disabled=0,
    )
    assert delivery.status is WebhookDeliveryStatus.FAILED
    assert delivery.failed_at is not None
    assert delivery.last_error_code == "http_rejected"


@pytest.mark.asyncio
async def test_worker_does_not_dispatch_to_disabled_endpoint(
    session: AsyncSession,
) -> None:
    """Queued work is disabled when its endpoint was administratively disabled."""
    delivery_id, _ = await _seed_delivery(
        session,
        endpoint_status=WebhookEndpointStatus.DISABLED,
    )
    dispatcher = _FakeDispatcher()

    result = await process_pending_webhook_deliveries(
        session,
        worker_id="webhook-worker-one",
        dispatcher=dispatcher,
    )

    delivery = await session.get(WebhookDelivery, delivery_id)
    assert delivery is not None

    assert result.claimed == 0
    assert not dispatcher.delivered_event_ids
    assert delivery.status is WebhookDeliveryStatus.DISABLED
    assert delivery.last_error_code == "endpoint_disabled"


@pytest.mark.asyncio
async def test_worker_empty_poll_has_zero_side_effects(
    session: AsyncSession,
) -> None:
    """An empty database poll is safe and does not invoke the dispatcher."""
    dispatcher = _FakeDispatcher()

    result = await process_pending_webhook_deliveries(
        session,
        worker_id="webhook-worker-one",
        dispatcher=dispatcher,
    )

    assert result == WebhookDeliveryProcessResult(
        claimed=0,
        delivered=0,
        retried=0,
        failed=0,
        disabled=0,
    )
    assert not dispatcher.delivered_event_ids
