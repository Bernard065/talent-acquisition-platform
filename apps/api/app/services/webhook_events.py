"""Transactional fan-out of privacy-safe business events to webhooks."""

from __future__ import annotations

from re import compile as re_compile

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.webhook import (
    WebhookDelivery,
    WebhookEndpoint,
    WebhookEvent,
    WebhookSubscription,
)
from app.db.transactions import transactional
from app.domains.webhooks.enums import WebhookEndpointStatus

_EVENT_TYPE_PATTERN = re_compile(r"^[a-z][a-z0-9_.-]{0,99}$")


def _validate_identifier(value: str, *, field_name: str, maximum_length: int) -> str:
    """Validate a bounded identifier without allowing empty values."""
    normalized = value.strip()

    if not normalized or len(normalized) > maximum_length:
        raise ValueError(f"{field_name} is invalid.")

    return normalized


def _validate_event_type(event_type: str) -> str:
    """Validate a stable, machine-readable event type."""
    normalized = event_type.strip()

    if not _EVENT_TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("Webhook event type is invalid.")

    return normalized


async def publish_webhook_event(
    session: AsyncSession,
    *,
    context: TenantContext,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    deduplication_key: str,
) -> WebhookEvent:
    """
    Persist one immutable event and create matching delivery intents atomically.

    Call this inside the same business transaction as the state change that the
    event represents. Repeated calls with the same tenant/event/key safely
    return the original event and create no duplicate deliveries.
    """
    normalized_event_type = _validate_event_type(event_type)
    normalized_aggregate_type = _validate_identifier(
        aggregate_type,
        field_name="Webhook aggregate type",
        maximum_length=100,
    )
    normalized_aggregate_id = _validate_identifier(
        aggregate_id,
        field_name="Webhook aggregate ID",
        maximum_length=100,
    )
    normalized_deduplication_key = _validate_identifier(
        deduplication_key,
        field_name="Webhook deduplication key",
        maximum_length=255,
    )

    async with transactional(session):
        statement = (
            insert(WebhookEvent)
            .values(
                tenant_id=context.tenant_id,
                event_type=normalized_event_type,
                aggregate_type=normalized_aggregate_type,
                aggregate_id=normalized_aggregate_id,
                deduplication_key=normalized_deduplication_key,
                payload={},
            )
            .on_conflict_do_nothing(
                constraint="uq_webhook_events_tenant_event_deduplication"
            )
            .returning(WebhookEvent.id)
        )
        webhook_event_id = await session.scalar(statement)

        if webhook_event_id is None:
            existing_event = await session.scalar(
                select(WebhookEvent).where(
                    WebhookEvent.tenant_id == context.tenant_id,
                    WebhookEvent.event_type == normalized_event_type,
                    WebhookEvent.deduplication_key
                    == normalized_deduplication_key,
                )
            )
            if existing_event is None:
                raise RuntimeError("Webhook event could not be created or loaded.")

            return existing_event

        webhook_event = await session.get(WebhookEvent, webhook_event_id)
        if webhook_event is None:
            raise RuntimeError("Webhook event could not be loaded.")

        endpoint_ids = list(
            await session.scalars(
                select(WebhookEndpoint.id)
                .join(
                    WebhookSubscription,
                    WebhookSubscription.webhook_endpoint_id
                    == WebhookEndpoint.id,
                )
                .where(
                    WebhookEndpoint.tenant_id == context.tenant_id,
                    WebhookEndpoint.status == WebhookEndpointStatus.ACTIVE,
                    WebhookSubscription.tenant_id == context.tenant_id,
                    WebhookSubscription.enabled.is_(True),
                    WebhookSubscription.event_type == normalized_event_type,
                )
                .order_by(WebhookEndpoint.id)
            )
        )

        session.add_all(
            [
                WebhookDelivery(
                    tenant_id=context.tenant_id,
                    webhook_endpoint_id=endpoint_id,
                    webhook_event_id=webhook_event.id,
                    event_type=normalized_event_type,
                )
                for endpoint_id in endpoint_ids
            ]
        )
        await session.flush()

    return webhook_event
