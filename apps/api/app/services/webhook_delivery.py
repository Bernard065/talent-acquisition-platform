"""Durable database claim and retry operations for webhook deliveries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from re import compile as re_compile
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.webhook import WebhookDelivery, WebhookEndpoint
from app.db.transactions import transactional
from app.domains.webhooks.enums import (
    WebhookDeliveryStatus,
    WebhookEndpointStatus,
)
from app.services.webhook_delivery_errors import (
    WebhookDeliveryLeaseLostError,
    WebhookDeliveryNotFoundError,
)

_FAILURE_CODE_PATTERN = re_compile(r"^[a-z0-9][a-z0-9_.-]{0,99}$")


@dataclass(frozen=True, slots=True)
class WebhookDeliveryPolicy:
    """Lease and retry limits for reliable webhook delivery workers."""

    batch_size: int = 25
    max_attempts: int = 8
    visibility_timeout: timedelta = timedelta(minutes=5)
    base_retry_delay: timedelta = timedelta(seconds=30)
    maximum_retry_delay: timedelta = timedelta(hours=1)

    def __post_init__(self) -> None:
        if not 1 <= self.batch_size <= 100:
            raise ValueError("Webhook delivery batch size must be between 1 and 100.")

        if not 1 <= self.max_attempts <= 100:
            raise ValueError("Webhook delivery max attempts must be between 1 and 100.")

        if self.visibility_timeout <= timedelta():
            raise ValueError("Webhook delivery visibility timeout must be positive.")

        if self.base_retry_delay <= timedelta():
            raise ValueError("Webhook delivery retry delay must be positive.")

        if self.maximum_retry_delay < self.base_retry_delay:
            raise ValueError(
                "Webhook delivery maximum retry delay must not be smaller than base."
            )


DEFAULT_WEBHOOK_DELIVERY_POLICY = WebhookDeliveryPolicy()


def _now() -> datetime:
    """Return a timezone-aware current timestamp."""
    return datetime.now(UTC)


def _validate_worker_id(worker_id: str) -> str:
    """Validate the worker identifier persisted in a lease."""
    normalized = worker_id.strip()

    if not normalized or len(normalized) > 255:
        raise ValueError("Webhook delivery worker ID is invalid.")

    return normalized


def _validate_failure_code(failure_code: str) -> str:
    """Accept only short safe failure classifications, never exception text."""
    normalized = failure_code.strip().lower()

    if not _FAILURE_CODE_PATTERN.fullmatch(normalized):
        raise ValueError("Webhook delivery failure code is invalid.")

    return normalized


def _retry_delay(
    *,
    delivery_id: UUID,
    attempts: int,
    policy: WebhookDeliveryPolicy,
) -> timedelta:
    """Return deterministic exponential backoff with bounded jitter."""
    exponential = policy.base_retry_delay * (2 ** max(attempts - 1, 0))
    capped = min(exponential, policy.maximum_retry_delay)

    # Deterministic jitter makes retries less synchronized and tests reproducible.
    jitter_seed = sha256(f"{delivery_id}:{attempts}".encode()).digest()[0]
    multiplier = 0.5 + (jitter_seed / 255)
    jittered = cast(timedelta, capped * multiplier)

    return min(jittered, policy.maximum_retry_delay)


async def claim_webhook_deliveries(
    session: AsyncSession,
    *,
    worker_id: str,
    policy: WebhookDeliveryPolicy = DEFAULT_WEBHOOK_DELIVERY_POLICY,
) -> list[WebhookDelivery]:
    """Recover stale leases and claim a bounded set of ready deliveries."""
    normalized_worker_id = _validate_worker_id(worker_id)
    now = _now()
    stale_before = now - policy.visibility_timeout

    async with transactional(session):
        disabled_endpoint_ids = select(WebhookEndpoint.id).where(
            WebhookEndpoint.status == WebhookEndpointStatus.DISABLED
        )

        await session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.status.in_(
                    (
                        WebhookDeliveryStatus.PENDING,
                        WebhookDeliveryStatus.DELIVERING,
                    )
                ),
                WebhookDelivery.webhook_endpoint_id.in_(disabled_endpoint_ids),
            )
            .values(
                status=WebhookDeliveryStatus.DISABLED,
                locked_at=None,
                locked_by=None,
                last_error_code="endpoint_disabled",
            )
        )

        await session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.DELIVERING,
                WebhookDelivery.locked_at.is_not(None),
                WebhookDelivery.locked_at < stale_before,
                WebhookDelivery.attempts >= policy.max_attempts,
            )
            .values(
                status=WebhookDeliveryStatus.FAILED,
                locked_at=None,
                locked_by=None,
                failed_at=now,
                last_error_code="lease_expired",
            )
        )

        await session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.DELIVERING,
                WebhookDelivery.locked_at.is_not(None),
                WebhookDelivery.locked_at < stale_before,
                WebhookDelivery.attempts < policy.max_attempts,
            )
            .values(
                status=WebhookDeliveryStatus.PENDING,
                locked_at=None,
                locked_by=None,
                next_attempt_at=now,
                last_error_code="lease_expired",
            )
        )

        deliveries = list(
            await session.scalars(
                select(WebhookDelivery)
                .join(
                    WebhookEndpoint,
                    WebhookEndpoint.id == WebhookDelivery.webhook_endpoint_id,
                )
                .where(
                    WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                    WebhookDelivery.next_attempt_at <= now,
                    WebhookEndpoint.status == WebhookEndpointStatus.ACTIVE,
                )
                .order_by(
                    WebhookDelivery.next_attempt_at,
                    WebhookDelivery.created_at,
                    WebhookDelivery.id,
                )
                .with_for_update(skip_locked=True, of=WebhookDelivery)
                .limit(policy.batch_size)
            )
        )

        for delivery in deliveries:
            delivery.status = WebhookDeliveryStatus.DELIVERING
            delivery.locked_at = now
            delivery.locked_by = normalized_worker_id
            delivery.attempts += 1

        await session.flush()

    return deliveries


async def mark_webhook_delivery_delivered(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    worker_id: str,
    response_status_code: int,
) -> WebhookDelivery:
    """Mark a worker-owned delivery as successfully delivered."""
    if not 100 <= response_status_code <= 599:
        raise ValueError("Webhook response status code is invalid.")

    async with transactional(session):
        delivery = await _get_leased_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=_validate_worker_id(worker_id),
        )
        delivery.status = WebhookDeliveryStatus.DELIVERED
        delivery.delivered_at = _now()
        delivery.response_status_code = response_status_code
        delivery.locked_at = None
        delivery.locked_by = None
        delivery.last_error_code = None
        await session.flush()

    return delivery


async def retry_or_fail_webhook_delivery(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    worker_id: str,
    failure_code: str,
    policy: WebhookDeliveryPolicy = DEFAULT_WEBHOOK_DELIVERY_POLICY,
) -> WebhookDelivery:
    """Release a retryable delivery or terminally fail it after its retry budget."""
    normalized_worker_id = _validate_worker_id(worker_id)
    normalized_failure_code = _validate_failure_code(failure_code)
    now = _now()

    async with transactional(session):
        delivery = await _get_leased_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=normalized_worker_id,
        )
        delivery.locked_at = None
        delivery.locked_by = None
        delivery.last_error_code = normalized_failure_code

        if delivery.attempts >= policy.max_attempts:
            delivery.status = WebhookDeliveryStatus.FAILED
            delivery.failed_at = now
        else:
            delivery.status = WebhookDeliveryStatus.PENDING
            delivery.next_attempt_at = now + _retry_delay(
                delivery_id=delivery.id,
                attempts=delivery.attempts,
                policy=policy,
            )

        await session.flush()

    return delivery


async def fail_webhook_delivery(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    worker_id: str,
    failure_code: str,
) -> WebhookDelivery:
    """Terminally fail a worker-owned delivery without retrying it."""
    async with transactional(session):
        delivery = await _get_leased_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=_validate_worker_id(worker_id),
        )
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.failed_at = _now()
        delivery.locked_at = None
        delivery.locked_by = None
        delivery.last_error_code = _validate_failure_code(failure_code)
        await session.flush()

    return delivery


async def disable_webhook_delivery(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    worker_id: str,
) -> WebhookDelivery:
    """Stop a leased delivery when its endpoint was disabled after claiming."""
    async with transactional(session):
        delivery = await _get_leased_delivery(
            session,
            delivery_id=delivery_id,
            worker_id=_validate_worker_id(worker_id),
        )
        delivery.status = WebhookDeliveryStatus.DISABLED
        delivery.locked_at = None
        delivery.locked_by = None
        delivery.last_error_code = "endpoint_disabled"
        await session.flush()

    return delivery


async def _get_leased_delivery(
    session: AsyncSession,
    *,
    delivery_id: UUID,
    worker_id: str,
) -> WebhookDelivery:
    """Load a delivery only if it remains leased by the current worker."""
    delivery = await session.scalar(
        select(WebhookDelivery)
        .where(WebhookDelivery.id == delivery_id)
        .with_for_update()
    )
    if delivery is None:
        raise WebhookDeliveryNotFoundError("Webhook delivery was not found.")

    if (
        delivery.status is not WebhookDeliveryStatus.DELIVERING
        or delivery.locked_by != worker_id
    ):
        raise WebhookDeliveryLeaseLostError(
            "Webhook delivery is no longer leased by this worker."
        )

    return delivery
