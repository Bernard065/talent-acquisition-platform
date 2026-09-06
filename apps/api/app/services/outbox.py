"""Transactional outbox helpers for reliable asynchronous processing."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.db.models.outbox import OutboxEvent


def enqueue_outbox_event(
    session: AsyncSession,
    *,
    context: TenantContext,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    deduplication_key: str,
    payload: Mapping[str, Any],
) -> OutboxEvent:
    """
    Queue asynchronous work in the caller's existing transaction.

    The caller owns commit and rollback. This makes the state transition and
    outbox event atomic: either both persist or neither persists.
    """
    event = OutboxEvent(
        tenant_id=context.tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        deduplication_key=deduplication_key,
        payload=dict(payload),
    )
    session.add(event)
    return event
