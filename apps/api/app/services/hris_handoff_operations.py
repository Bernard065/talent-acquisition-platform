"""Tenant-admin read operations for private HRIS onboarding handoffs."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from app.core.authorization import Role, TenantContext
from app.db.models.hris import HrisConnection, HrisHandoff
from app.domains.hris.enums import HrisHandoffStatus, HrisProvider
from app.services.hris_errors import HrisAccessDeniedError
from app.services.hris_handoff_errors import (
    HrisHandoffNotFoundError,
    HrisHandoffValidationError,
    InvalidHrisHandoffCursorError,
)

_MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class HrisHandoffOperation:
    """A private, tenant-scoped HRIS handoff and its provider identity."""

    handoff: HrisHandoff
    provider: HrisProvider


@dataclass(frozen=True, slots=True)
class HrisHandoffOperationPage:
    """One deterministic page of private HRIS handoff operations."""

    items: tuple[HrisHandoffOperation, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _Cursor:
    """Opaque pagination position."""

    updated_at: datetime
    handoff_id: UUID


def _require_tenant_admin(context: TenantContext) -> None:
    if Role.TENANT_ADMIN not in context.roles:
        raise HrisAccessDeniedError("Tenant administrator access is required.")


def _normalise_time_bound(value: datetime | None, *, field_name: str) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        raise HrisHandoffValidationError(
            f"{field_name} must include a timezone offset."
        )

    return value.astimezone(UTC)


def _encode_cursor(operation: HrisHandoffOperation) -> str:
    payload = {
        "updated_at": operation.handoff.updated_at.astimezone(UTC).isoformat(),
        "handoff_id": str(operation.handoff.id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> _Cursor:
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(
            base64.urlsafe_b64decode(padded_cursor.encode("ascii")).decode("utf-8")
        )
        updated_at = datetime.fromisoformat(payload["updated_at"])
        handoff_id = UUID(payload["handoff_id"])
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as error:
        raise InvalidHrisHandoffCursorError(
            "The HRIS handoff cursor is invalid."
        ) from error

    if updated_at.tzinfo is None:
        raise InvalidHrisHandoffCursorError(
            "The HRIS handoff cursor is invalid."
        )

    return _Cursor(
        updated_at=updated_at.astimezone(UTC),
        handoff_id=handoff_id,
    )


def _base_statement(context: TenantContext) -> Select:  # type: ignore[type-arg]
    return (
        select(HrisHandoff, HrisConnection.provider)
        .join(
            HrisConnection,
            and_(
                HrisConnection.id == HrisHandoff.hris_connection_id,
                HrisConnection.tenant_id == HrisHandoff.tenant_id,
            ),
        )
        .where(HrisHandoff.tenant_id == context.tenant_id)
    )


async def list_hris_handoff_operations(
    session: AsyncSession,
    *,
    context: TenantContext,
    status: HrisHandoffStatus | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> HrisHandoffOperationPage:
    """List safe, tenant-local handoff operational records for administrators."""
    _require_tenant_admin(context)

    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise HrisHandoffValidationError(
            f"limit must be between 1 and {_MAX_PAGE_SIZE}."
        )

    created_from = _normalise_time_bound(created_from, field_name="created_from")
    created_to = _normalise_time_bound(created_to, field_name="created_to")

    if created_from is not None and created_to is not None and created_from > created_to:
        raise HrisHandoffValidationError(
            "created_from must be earlier than or equal to created_to."
        )

    statement = _base_statement(context)

    if status is not None:
        statement = statement.where(HrisHandoff.status == status)

    if created_from is not None:
        statement = statement.where(HrisHandoff.created_at >= created_from)

    if created_to is not None:
        statement = statement.where(HrisHandoff.created_at <= created_to)

    if cursor is not None:
        position = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                HrisHandoff.updated_at < position.updated_at,
                and_(
                    HrisHandoff.updated_at == position.updated_at,
                    HrisHandoff.id < position.handoff_id,
                ),
            )
        )

    statement = statement.order_by(
        HrisHandoff.updated_at.desc(),
        HrisHandoff.id.desc(),
    ).limit(limit + 1)

    result = await session.execute(statement)
    rows = result.tuples().all()

    operations = tuple(
        HrisHandoffOperation(handoff=row[0], provider=row[1])
        for row in rows[:limit]
    )

    next_cursor = (
        _encode_cursor(operations[-1])
        if len(rows) > limit and operations
        else None
    )

    return HrisHandoffOperationPage(
        items=operations,
        next_cursor=next_cursor,
    )


async def get_hris_handoff_operation(
    session: AsyncSession,
    *,
    context: TenantContext,
    handoff_id: UUID,
) -> HrisHandoffOperation:
    """Return one safe tenant-local handoff operation for an administrator."""
    _require_tenant_admin(context)

    statement = _base_statement(context).where(HrisHandoff.id == handoff_id)
    result = await session.execute(statement)
    row = result.tuples().one_or_none()

    if row is None:
        raise HrisHandoffNotFoundError("HRIS handoff not found.")

    return HrisHandoffOperation(handoff=row[0], provider=row[1])
