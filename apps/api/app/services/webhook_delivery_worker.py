"""Orchestration for durable signed webhook delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
)
from app.domains.webhooks.enums import WebhookEndpointStatus
from app.services.webhook_delivery import (
    DEFAULT_WEBHOOK_DELIVERY_POLICY,
    WebhookDeliveryPolicy,
    claim_webhook_deliveries,
    disable_webhook_delivery,
    fail_webhook_delivery,
    mark_webhook_delivery_delivered,
    retry_or_fail_webhook_delivery,
)
from app.services.webhook_delivery_errors import WebhookDeliveryTransportError


class WebhookDeliveryDispatcher(Protocol):
    """Port implemented by the signed outbound HTTP adapter."""

    async def deliver(
        self,
        *,
        endpoint: WebhookEndpoint,
        webhook_event: WebhookEvent,
    ) -> int:
        """Deliver one immutable webhook event."""


@dataclass(frozen=True, slots=True)
class WebhookDeliveryProcessResult:
    """Counts from one bounded worker poll cycle."""

    claimed: int
    delivered: int
    retried: int
    failed: int
    disabled: int


async def process_pending_webhook_deliveries(
    session: AsyncSession,
    *,
    worker_id: str,
    dispatcher: WebhookDeliveryDispatcher,
    policy: WebhookDeliveryPolicy = DEFAULT_WEBHOOK_DELIVERY_POLICY,
) -> WebhookDeliveryProcessResult:
    """Claim and process a bounded batch of webhook deliveries."""
    claimed_deliveries = await claim_webhook_deliveries(
        session,
        worker_id=worker_id,
        policy=policy,
    )

    delivered = 0
    retried = 0
    failed = 0
    disabled = 0

    for claimed_delivery in claimed_deliveries:
        current_delivery = await session.get(
            WebhookDelivery,
            claimed_delivery.id,
        )
        if current_delivery is None:
            continue

        endpoint = await session.get(
            WebhookEndpoint,
            current_delivery.webhook_endpoint_id,
        )
        webhook_event = await session.get(
            WebhookEvent,
            current_delivery.webhook_event_id,
        )

        if endpoint is None or webhook_event is None:
            await fail_webhook_delivery(
                session,
                delivery_id=current_delivery.id,
                worker_id=worker_id,
                failure_code="source_missing",
            )
            failed += 1
            continue

        if endpoint.status is WebhookEndpointStatus.DISABLED:
            await disable_webhook_delivery(
                session,
                delivery_id=current_delivery.id,
                worker_id=worker_id,
            )
            disabled += 1
            continue

        try:
            response_status_code = await dispatcher.deliver(
                endpoint=endpoint,
                webhook_event=webhook_event,
            )
        except WebhookDeliveryTransportError as error:
            if error.retryable:
                updated_delivery = await retry_or_fail_webhook_delivery(
                    session,
                    delivery_id=current_delivery.id,
                    worker_id=worker_id,
                    failure_code=error.code,
                    policy=policy,
                )
                if updated_delivery.status.value == "failed":
                    failed += 1
                else:
                    retried += 1
            else:
                await fail_webhook_delivery(
                    session,
                    delivery_id=current_delivery.id,
                    worker_id=worker_id,
                    failure_code=error.code,
                )
                failed += 1
        except Exception:  # pylint: disable=broad-exception-caught
            updated_delivery = await retry_or_fail_webhook_delivery(
                session,
                delivery_id=current_delivery.id,
                worker_id=worker_id,
                failure_code="unexpected_error",
                policy=policy,
            )
            if updated_delivery.status.value == "failed":
                failed += 1
            else:
                retried += 1
        else:
            await mark_webhook_delivery_delivered(
                session,
                delivery_id=current_delivery.id,
                worker_id=worker_id,
                response_status_code=response_status_code,
            )
            delivered += 1

    return WebhookDeliveryProcessResult(
        claimed=len(claimed_deliveries),
        delivered=delivered,
        retried=retried,
        failed=failed,
        disabled=disabled,
    )
