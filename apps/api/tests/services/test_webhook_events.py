"""PostgreSQL integration tests for transactional webhook event fan-out."""

from __future__ import annotations

import inspect
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.identity import Tenant
from app.db.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookSubscription,
)
from app.domains.webhooks.enums import WebhookEndpointStatus
from app.services.webhook_events import publish_webhook_event


def _context(tenant_id: UUID) -> TenantContext:
    """Build a verified tenant-admin context for a test tenant."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="webhook-publisher-subject",
        roles=frozenset({Role.TENANT_ADMIN}),
        request_id="webhook-event-test-request",
    )


async def _seed_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Create one tenant required by webhook foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Webhook Event Tenant {tenant_id.hex[:12]}",
            slug=f"webhook-event-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


async def _seed_endpoint(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    event_types: tuple[str, ...],
    status: WebhookEndpointStatus = WebhookEndpointStatus.ACTIVE,
) -> WebhookEndpoint:
    """Create one endpoint and its subscriptions directly for fan-out tests."""
    endpoint = WebhookEndpoint(
        tenant_id=tenant_id,
        name=f"Endpoint {uuid4().hex[:8]}",
        url="https://hooks.partner.example.test/tap",
        credential_reference=f"tap-webhook-{uuid4().hex}",
        status=status,
        created_by_subject="tenant-admin-subject",
    )
    session.add(endpoint)
    await session.flush()

    session.add_all(
        [
            WebhookSubscription(
                tenant_id=tenant_id,
                webhook_endpoint_id=endpoint.id,
                event_type=event_type,
            )
            for event_type in event_types
        ]
    )
    await session.commit()

    return endpoint


@pytest.mark.asyncio
async def test_fans_out_to_each_matching_active_subscription(
    session: AsyncSession,
) -> None:
    """One event creates exactly one delivery for every matching endpoint."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    first = await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("application.hired",),
    )
    second = await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("application.hired", "offer.accepted"),
    )
    await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("offer.accepted",),
    )

    event = await publish_webhook_event(
        session,
        context=_context(tenant_id),
        event_type="application.hired",
        aggregate_type="application",
        aggregate_id=str(uuid4()),
        deduplication_key=f"application-hired:{uuid4()}",
    )

    deliveries = list(
        await session.scalars(
            select(WebhookDelivery)
            .where(WebhookDelivery.webhook_event_id == event.id)
            .order_by(WebhookDelivery.webhook_endpoint_id)
        )
    )

    assert {delivery.webhook_endpoint_id for delivery in deliveries} == {
        first.id,
        second.id,
    }
    assert all(delivery.tenant_id == tenant_id for delivery in deliveries)
    assert all(delivery.event_type == "application.hired" for delivery in deliveries)


@pytest.mark.asyncio
async def test_excludes_disabled_endpoints_and_disabled_subscriptions(
    session: AsyncSession,
) -> None:
    """Only active endpoints with enabled matching subscriptions receive events."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    active_endpoint = await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("offer.accepted",),
    )
    await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("offer.accepted",),
        status=WebhookEndpointStatus.DISABLED,
    )
    disabled_subscription_endpoint = await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("offer.accepted",),
    )

    subscription = await session.scalar(
        select(WebhookSubscription).where(
            WebhookSubscription.webhook_endpoint_id
            == disabled_subscription_endpoint.id
        )
    )
    assert subscription is not None
    subscription.enabled = False
    await session.commit()

    event = await publish_webhook_event(
        session,
        context=_context(tenant_id),
        event_type="offer.accepted",
        aggregate_type="offer",
        aggregate_id=str(uuid4()),
        deduplication_key=f"offer-accepted:{uuid4()}",
    )

    deliveries = list(
        await session.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_event_id == event.id
            )
        )
    )

    assert len(deliveries) == 1
    assert deliveries[0].webhook_endpoint_id == active_endpoint.id


@pytest.mark.asyncio
async def test_never_fans_out_across_tenants(
    session: AsyncSession,
) -> None:
    """A tenant event can match subscriptions belonging only to that tenant."""
    first_tenant_id = uuid4()
    second_tenant_id = uuid4()
    await _seed_tenant(session, first_tenant_id)
    await _seed_tenant(session, second_tenant_id)

    first_endpoint = await _seed_endpoint(
        session,
        tenant_id=first_tenant_id,
        event_types=("application.hired",),
    )
    second_endpoint = await _seed_endpoint(
        session,
        tenant_id=second_tenant_id,
        event_types=("application.hired",),
    )

    event = await publish_webhook_event(
        session,
        context=_context(first_tenant_id),
        event_type="application.hired",
        aggregate_type="application",
        aggregate_id=str(uuid4()),
        deduplication_key=f"application-hired:{uuid4()}",
    )

    deliveries = list(
        await session.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_event_id == event.id
            )
        )
    )

    assert len(deliveries) == 1
    assert deliveries[0].webhook_endpoint_id == first_endpoint.id
    assert deliveries[0].webhook_endpoint_id != second_endpoint.id
    assert deliveries[0].tenant_id == first_tenant_id


@pytest.mark.asyncio
async def test_duplicate_event_is_idempotent(
    session: AsyncSession,
) -> None:
    """A retried business action returns the original event and delivery."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    await _seed_endpoint(
        session,
        tenant_id=tenant_id,
        event_types=("offer.accepted",),
    )

    deduplication_key = f"offer-accepted:{uuid4()}"
    aggregate_id = str(uuid4())

    first = await publish_webhook_event(
        session,
        context=_context(tenant_id),
        event_type="offer.accepted",
        aggregate_type="offer",
        aggregate_id=aggregate_id,
        deduplication_key=deduplication_key,
    )
    second = await publish_webhook_event(
        session,
        context=_context(tenant_id),
        event_type="offer.accepted",
        aggregate_type="offer",
        aggregate_id=aggregate_id,
        deduplication_key=deduplication_key,
    )

    events = list(
        await session.scalars(
            select(WebhookEvent).where(
                WebhookEvent.tenant_id == tenant_id,
                WebhookEvent.event_type == "offer.accepted",
            )
        )
    )
    deliveries = list(
        await session.scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_event_id == first.id
            )
        )
    )

    assert first.id == second.id
    assert len(events) == 1
    assert len(deliveries) == 1


@pytest.mark.asyncio
async def test_event_contract_cannot_accept_arbitrary_candidate_payloads(
    session: AsyncSession,
) -> None:
    """Webhook events contain only safe metadata, never caller-provided PII."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    signature = inspect.signature(publish_webhook_event)
    assert "payload" not in signature.parameters

    event = await publish_webhook_event(
        session,
        context=_context(tenant_id),
        event_type="application.hired",
        aggregate_type="application",
        aggregate_id=str(uuid4()),
        deduplication_key=f"application-hired:{uuid4()}",
    )

    assert event.payload == {}
    assert event.aggregate_type == "application"
    assert event.event_type == "application.hired"
