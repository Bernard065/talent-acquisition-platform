"""Tenant-scoped application services for requisition CRUD operations."""

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.requisition import Requisition
from app.db.transactions import transactional
from app.domains.requisitions.enums import RequisitionStatus
from app.services.audit import record_audit_event
from app.services.requisition_errors import (
    InvalidRequisitionCursorError,
    RequisitionAccessDeniedError,
    RequisitionNotEditableError,
    RequisitionNotFoundError,
)

_READ_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
        Role.HIRING_MANAGER,
        Role.ANALYST,
    }
)

_WRITE_ROLES = frozenset(
    {
        Role.TENANT_ADMIN,
        Role.RECRUITER,
    }
)

_MUTABLE_FIELDS = frozenset(
    {
        "title",
        "description",
        "department",
        "location",
        "headcount",
    }
)


@dataclass(frozen=True, slots=True)
class CreateRequisitionCommand:
    """Validated business input for creating a requisition."""

    title: str
    description: str | None
    department: str | None
    location: str | None
    headcount: int


@dataclass(frozen=True, slots=True)
class UpdateRequisitionCommand:
    """Validated changes for an editable requisition."""

    changes: Mapping[str, str | int | None]

    def __post_init__(self) -> None:
        unknown_fields = self.changes.keys() - _MUTABLE_FIELDS
        if unknown_fields:
            raise ValueError(
                f"Unsupported requisition fields: {', '.join(sorted(unknown_fields))}."
            )

        if not self.changes:
            raise ValueError("At least one requisition field must be supplied.")


@dataclass(frozen=True, slots=True)
class RequisitionPage:
    """A keyset-paginated page of tenant requisitions."""

    items: list[Requisition]
    next_cursor: str | None


def _require_any_role(
    context: TenantContext,
    allowed_roles: frozenset[Role],
) -> None:
    """Enforce a service-level authorization boundary."""
    if context.roles.isdisjoint(allowed_roles):
        raise RequisitionAccessDeniedError(
            "Caller is not permitted to perform this requisition operation."
        )


def _encode_cursor(requisition: Requisition) -> str:
    """Encode the final item in a page as an opaque keyset cursor."""
    updated_at = requisition.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)

    payload = json.dumps(
        {
            "id": str(requisition.id),
            "updated_at": updated_at.isoformat(),
        },
        separators=(",", ":"),
    ).encode()

    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode and validate an opaque keyset cursor."""
    try:
        padded_cursor = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_cursor))
        updated_at = datetime.fromisoformat(payload["updated_at"])
        requisition_id = UUID(payload["id"])

        if updated_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")

        return updated_at, requisition_id
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as error:
        raise InvalidRequisitionCursorError(
            "Invalid requisition cursor."
        ) from error


async def create_requisition(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateRequisitionCommand,
) -> Requisition:
    """Create a draft requisition and its audit record atomically."""
    _require_any_role(context, _WRITE_ROLES)

    async with transactional(session):
        requisition = Requisition(
            tenant_id=context.tenant_id,
            title=command.title,
            description=command.description,
            department=command.department,
            location=command.location,
            headcount=command.headcount,
            status=RequisitionStatus.DRAFT,
            created_by_subject=context.subject,
        )
        session.add(requisition)
        await session.flush()
        await session.refresh(requisition)

        record_audit_event(
            session,
            context=context,
            action="requisition.created",
            entity_type="requisition",
            entity_id=str(requisition.id),
            details={
                "status": requisition.status.value,
                "version": requisition.version,
            },
        )

    return requisition


async def get_requisition(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
) -> Requisition:
    """Return one requisition visible to the caller's tenant."""
    _require_any_role(context, _READ_ROLES)

    requisition = await session.scalar(
        select(Requisition).where(
            Requisition.id == requisition_id,
            Requisition.tenant_id == context.tenant_id,
        )
    )

    if requisition is None:
        raise RequisitionNotFoundError("Requisition was not found.")

    return requisition


async def list_requisitions(
    session: AsyncSession,
    *,
    context: TenantContext,
    limit: int = 50,
    cursor: str | None = None,
) -> RequisitionPage:
    """Return a tenant-scoped, keyset-paginated requisition page."""
    _require_any_role(context, _READ_ROLES)

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")

    statement = select(Requisition).where(
        Requisition.tenant_id == context.tenant_id
    )

    if cursor is not None:
        cursor_updated_at, cursor_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                Requisition.updated_at < cursor_updated_at,
                and_(
                    Requisition.updated_at == cursor_updated_at,
                    Requisition.id < cursor_id,
                ),
            )
        )

    statement = statement.order_by(
        Requisition.updated_at.desc(),
        Requisition.id.desc(),
    ).limit(limit + 1)

    requisitions = list((await session.scalars(statement)).all())
    has_next_page = len(requisitions) > limit
    items = requisitions[:limit]

    return RequisitionPage(
        items=items,
        next_cursor=_encode_cursor(items[-1]) if has_next_page else None,
    )


async def update_requisition(
    session: AsyncSession,
    *,
    context: TenantContext,
    requisition_id: UUID,
    command: UpdateRequisitionCommand,
) -> Requisition:
    """Update a draft requisition and record the change atomically."""
    _require_any_role(context, _WRITE_ROLES)

    async with transactional(session):
        requisition = await session.scalar(
            select(Requisition)
            .where(
                Requisition.id == requisition_id,
                Requisition.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )

        if requisition is None:
            raise RequisitionNotFoundError("Requisition was not found.")

        if requisition.status is not RequisitionStatus.DRAFT:
            raise RequisitionNotEditableError(
                "Only draft requisitions can be edited."
            )

        for field_name, value in command.changes.items():
            setattr(requisition, field_name, value)

        await session.flush()
        await session.refresh(requisition)

        record_audit_event(
            session,
            context=context,
            action="requisition.updated",
            entity_type="requisition",
            entity_id=str(requisition.id),
            details={
                "changed_fields": sorted(command.changes),
                "version": requisition.version,
            },
        )

    return requisition
