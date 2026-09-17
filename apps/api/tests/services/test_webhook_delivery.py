"""PostgreSQL tests for webhook delivery leases, retries, and terminal states."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

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
from app.services.webhook_delivery import (
    WebhookDeliveryPolicy,
    claim_webhook_deliveries,
    fail_webhook_delivery,
    retry_or_fail_webhook_delivery,
)


@pytest_asyncio.fixture(name="webhook_session_factory")
async def webhook_session_factory_fixture(
    database_engine: AsyncEngine,
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Provide independent sessions for lock and concurrency tests."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    yield session_factory

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )


async def _seed_deliveries(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    count: int,
    endpoint_status: WebhookEndpointStatus = WebhookEndpointStatus.ACTIVE,
    delivery_status: WebhookDeliveryStatus = WebhookDeliveryStatus.PENDING,
    attempts: int = 0,
    locked_at: datetime | None = None,
    locked_by: str | None = None,
) -> tuple[UUID, list[UUID]]:
    """Create a tenant, endpoint, immutable events, and pending deliveries."""
    tenant_id = uuid4()
    delivery_ids: list[UUID] = []
    now = datetime.now(UTC)

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Webhook Delivery Tenant {tenant_id.hex[:12]}",
                slug=f"webhook-delivery-{tenant_id.hex[:12]}",
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

        for position in range(count):
            event = WebhookEvent(
                tenant_id=tenant_id,
                event_type="application.hired",
                aggregate_type="application",
                aggregate_id=str(uuid4()),
                deduplication_key=f"application-hired:{tenant_id}:{position}",
                payload={},
            )
            session.add(event)
            await session.flush()

            delivery = WebhookDelivery(
                tenant_id=tenant_id,
                webhook_endpoint_id=endpoint.id,
                webhook_event_id=event.id,
                event_type=event.event_type,
                status=delivery_status,
                attempts=attempts,
                locked_at=locked_at,
                locked_by=locked_by,
                next_attempt_at=now - timedelta(seconds=1),
            )
            session.add(delivery)
            await session.flush()
            delivery_ids.append(delivery.id)

    return tenant_id, delivery_ids


async def _get_delivery(
    session_factory: async_sessionmaker[AsyncSession],
    delivery_id: UUID,
) -> WebhookDelivery:
    """Load a delivery after another session commits its worker operation."""
    async with session_factory() as session:
        delivery = await session.get(WebhookDelivery, delivery_id)
        assert delivery is not None
        return delivery


@pytest.mark.asyncio
async def test_skip_locked_allows_second_worker_to_claim_another_delivery(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Concurrent workers do not block each other or claim the same row."""
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=2,
    )
    locked_delivery_id, available_delivery_id = delivery_ids
    policy = WebhookDeliveryPolicy(batch_size=1)

    async with webhook_session_factory() as locking_session:
        async with locking_session.begin():
            locked_delivery = await locking_session.scalar(
                select(WebhookDelivery)
                .where(WebhookDelivery.id == locked_delivery_id)
                .with_for_update()
            )
            assert locked_delivery is not None

            async with webhook_session_factory() as worker_session:
                claimed = await claim_webhook_deliveries(
                    worker_session,
                    worker_id="worker-two",
                    policy=policy,
                )

    assert [delivery.id for delivery in claimed] == [available_delivery_id]


@pytest.mark.asyncio
async def test_recovers_stale_lease_and_reclaims_delivery(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A crashed worker lease becomes eligible for a later worker."""
    stale_at = datetime.now(UTC) - timedelta(minutes=10)
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=1,
        delivery_status=WebhookDeliveryStatus.DELIVERING,
        attempts=1,
        locked_at=stale_at,
        locked_by="crashed-worker",
    )
    policy = WebhookDeliveryPolicy(
        batch_size=1,
        max_attempts=3,
        visibility_timeout=timedelta(minutes=1),
    )

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="recovery-worker",
            policy=policy,
        )

    delivery = await _get_delivery(webhook_session_factory, delivery_ids[0])

    assert [item.id for item in claimed] == delivery_ids
    assert delivery.status is WebhookDeliveryStatus.DELIVERING
    assert delivery.locked_by == "recovery-worker"
    assert delivery.attempts == 2
    assert delivery.last_error_code == "lease_expired"


@pytest.mark.asyncio
async def test_retries_with_bounded_exponential_backoff_and_jitter(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Retry delay grows exponentially but remains within its jitter bounds."""
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=1,
    )
    policy = WebhookDeliveryPolicy(
        batch_size=1,
        max_attempts=4,
        base_retry_delay=timedelta(seconds=10),
        maximum_retry_delay=timedelta(seconds=60),
    )

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        retry_started_at = datetime.now(UTC)
        retried = await retry_or_fail_webhook_delivery(
            session,
            delivery_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="transport_timeout",
            policy=policy,
        )
        retry_finished_at = datetime.now(UTC)

    assert retried.status is WebhookDeliveryStatus.PENDING
    assert retried.attempts == 1
    assert retry_started_at + timedelta(seconds=5) <= retried.next_attempt_at
    assert retried.next_attempt_at <= retry_finished_at + timedelta(seconds=15)

    async with webhook_session_factory.begin() as session:
        delivery = await session.get(WebhookDelivery, delivery_ids[0])
        assert delivery is not None
        delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        second_retry_started_at = datetime.now(UTC)
        retried = await retry_or_fail_webhook_delivery(
            session,
            delivery_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="transport_timeout",
            policy=policy,
        )
        second_retry_finished_at = datetime.now(UTC)

    assert retried.status is WebhookDeliveryStatus.PENDING
    assert retried.attempts == 2
    assert second_retry_started_at + timedelta(seconds=10) <= retried.next_attempt_at
    assert retried.next_attempt_at <= second_retry_finished_at + timedelta(seconds=30)


@pytest.mark.asyncio
async def test_marks_delivery_failed_after_retry_budget_is_exhausted(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Exhausted retryable failures become terminal delivery failures."""
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=1,
    )
    policy = WebhookDeliveryPolicy(batch_size=1, max_attempts=1)

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="worker-one",
            policy=policy,
        )
        failed = await retry_or_fail_webhook_delivery(
            session,
            delivery_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="transport_timeout",
            policy=policy,
        )

    assert failed.id == delivery_ids[0]
    assert failed.status is WebhookDeliveryStatus.FAILED
    assert failed.failed_at is not None
    assert failed.locked_at is None
    assert failed.locked_by is None
    assert failed.last_error_code == "transport_timeout"


@pytest.mark.asyncio
async def test_marks_non_retryable_failure_terminally(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Permanent receiver failures do not consume the retry budget."""
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=1,
    )

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="worker-one",
        )
        failed = await fail_webhook_delivery(
            session,
            delivery_id=claimed[0].id,
            worker_id="worker-one",
            failure_code="http_rejected",
        )

    assert failed.id == delivery_ids[0]
    assert failed.status is WebhookDeliveryStatus.FAILED
    assert failed.failed_at is not None
    assert failed.last_error_code == "http_rejected"


@pytest.mark.asyncio
async def test_disables_pending_delivery_when_endpoint_is_disabled(
    webhook_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Disabled endpoints cannot receive a queued delivery later."""
    _, delivery_ids = await _seed_deliveries(
        webhook_session_factory,
        count=1,
        endpoint_status=WebhookEndpointStatus.DISABLED,
    )

    async with webhook_session_factory() as session:
        claimed = await claim_webhook_deliveries(
            session,
            worker_id="worker-one",
        )

    delivery = await _get_delivery(webhook_session_factory, delivery_ids[0])

    assert not claimed
    assert delivery.status is WebhookDeliveryStatus.DISABLED
    assert delivery.last_error_code == "endpoint_disabled"
    assert delivery.locked_at is None
    assert delivery.locked_by is None
