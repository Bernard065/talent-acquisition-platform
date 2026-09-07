"""Tenant-scoped operational inspection for dead-letter outbox events."""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.outbox import OutboxEvent
from app.domains.outbox.enums import OutboxEventStatus
from app.services.outbox_inspection_errors import (
    InvalidOutboxCursorError,
    OutboxInspectionAccessDeniedError,
)

_MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class DeadLetterPage:
    """A keyset-paginated tenant-local dead-letter event collection."""

    items: tuple[OutboxEvent, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _Cursor:
    """Internal keyset position; never treated as an authorization boundary."""

    dead_lettered_at: datetime
    event_id: UUID


def _require_tenant_admin(context: TenantContext) -> None:
    """Restrict operational inspection to tenant administrators."""
    if Role.TENANT_ADMIN not in context.roles:
        raise OutboxInspectionAccessDeniedError(
            "Caller is not permitted to inspect dead-letter events."
        )


def _encode_cursor(event: OutboxEvent) -> str:
    """Create an opaque cursor from a deterministic dead-letter ordering key."""
    if event.dead_lettered_at is None:
        raise RuntimeError("Dead-letter event is missing its timestamp.")

    payload = {
        "dead_lettered_at": event.dead_lettered_at.isoformat(),
        "event_id": str(event.id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")

    return encoded.rstrip("=")


def _decode_cursor(cursor: str) -> _Cursor:
    """Parse a cursor while rejecting malformed or timezone-naive values."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        )
        dead_lettered_at = datetime.fromisoformat(payload["dead_lettered_at"])
        event_id = UUID(payload["event_id"])
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise InvalidOutboxCursorError("Invalid outbox cursor.") from error

    if dead_lettered_at.tzinfo is None:
        raise InvalidOutboxCursorError("Invalid outbox cursor.")

    return _Cursor(
        dead_lettered_at=dead_lettered_at.astimezone(UTC),
        event_id=event_id,
    )


async def list_dead_letter_events(
    session: AsyncSession,
    *,
    context: TenantContext,
    limit: int = 50,
    cursor: str | None = None,
) -> DeadLetterPage:
    """
    Return operationally useful, tenant-scoped dead-letter records.

    The ORM records are intentionally kept internal. The API layer later
    serializes only safe fields and never exposes payloads or storage keys.
    """
    _require_tenant_admin(context)

    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise ValueError(f"Outbox list limit must be between 1 and {_MAX_PAGE_SIZE}.")

    statement = select(OutboxEvent).where(
        OutboxEvent.tenant_id == context.tenant_id,
        OutboxEvent.status == OutboxEventStatus.DEAD_LETTERED,
        OutboxEvent.dead_lettered_at.is_not(None),
    )

    if cursor is not None:
        position = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                OutboxEvent.dead_lettered_at < position.dead_lettered_at,
                and_(
                    OutboxEvent.dead_lettered_at == position.dead_lettered_at,
                    OutboxEvent.id < position.event_id,
                ),
            )
        )

    events = list(
        await session.scalars(
            statement.order_by(
                OutboxEvent.dead_lettered_at.desc(),
                OutboxEvent.id.desc(),
            ).limit(limit + 1)
        )
    )

    has_next_page = len(events) > limit
    items = tuple(events[:limit])

    return DeadLetterPage(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if has_next_page else None,
    )
