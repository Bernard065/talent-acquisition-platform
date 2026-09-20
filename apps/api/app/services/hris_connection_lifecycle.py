"""Tenant-admin lifecycle operations for HRIS connections."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.hris import HrisConnection
from app.db.transactions import transactional
from app.domains.hris.enums import HrisConnectionStatus
from app.services.audit import record_audit_event
from app.services.hris_errors import (
    HrisAccessDeniedError,
    HrisConnectionNotFoundError,
    HrisConnectionValidationError,
    HrisConnectionVersionConflictError,
)

_MAX_PAGE_SIZE = 100


def _require_tenant_admin(context: TenantContext) -> None:
    """Restrict HRIS configuration and lifecycle changes to tenant admins."""
    if Role.TENANT_ADMIN not in context.roles:
        raise HrisAccessDeniedError(
            "Tenant administrator permission is required for HRIS configuration."
        )


def _validate_expected_version(
    connection: HrisConnection,
    expected_version: int,
) -> None:
    """Reject stale lifecycle mutations before changing a locked row."""
    if expected_version < 1:
        raise HrisConnectionValidationError(
            "Expected HRIS connection version must be at least one."
        )

    if connection.version != expected_version:
        raise HrisConnectionVersionConflictError(
            "HRIS connection has changed; retrieve it and retry."
        )


async def _load_connection_for_update(
    session: AsyncSession,
    *,
    context: TenantContext,
    connection_id: UUID,
) -> HrisConnection:
    """Load and lock one non-deleted connection within the caller tenant."""
    connection = await session.scalar(
        select(HrisConnection)
        .where(
            HrisConnection.id == connection_id,
            HrisConnection.tenant_id == context.tenant_id,
            HrisConnection.deleted_at.is_(None),
        )
        .with_for_update()
    )

    if connection is None:
        raise HrisConnectionNotFoundError("HRIS connection was not found.")

    return connection


async def _reload_detached_connection(
    session: AsyncSession,
    *,
    connection_id: UUID,
) -> HrisConnection:
    """Refresh then detach a connection safe to inspect after commit."""
    connection = await session.get(HrisConnection, connection_id)
    if connection is None:
        raise HrisConnectionNotFoundError("HRIS connection was not found.")

    await session.refresh(connection)
    session.expunge(connection)
    return connection


async def get_hris_connection(
    session: AsyncSession,
    *,
    context: TenantContext,
    connection_id: UUID,
) -> HrisConnection:
    """Return one non-deleted tenant-owned HRIS connection."""
    _require_tenant_admin(context)

    connection = await session.scalar(
        select(HrisConnection).where(
            HrisConnection.id == connection_id,
            HrisConnection.tenant_id == context.tenant_id,
            HrisConnection.deleted_at.is_(None),
        )
    )
    if connection is None:
        raise HrisConnectionNotFoundError("HRIS connection was not found.")

    return connection


async def list_hris_connections(
    session: AsyncSession,
    *,
    context: TenantContext,
    limit: int = 50,
) -> tuple[HrisConnection, ...]:
    """List non-deleted connections without returning credential references."""
    _require_tenant_admin(context)

    if not 1 <= limit <= _MAX_PAGE_SIZE:
        raise HrisConnectionValidationError(
            f"HRIS connection limit must be between one and {_MAX_PAGE_SIZE}."
        )

    connections = list(
        await session.scalars(
            select(HrisConnection)
            .where(
                HrisConnection.tenant_id == context.tenant_id,
                HrisConnection.deleted_at.is_(None),
            )
            .order_by(HrisConnection.created_at.desc(), HrisConnection.id.desc())
            .limit(limit)
        )
    )

    return tuple(connections)


async def disable_hris_connection(
    session: AsyncSession,
    *,
    context: TenantContext,
    connection_id: UUID,
    expected_version: int,
) -> HrisConnection:
    """Disable a connection so future onboarding starts cannot queue handoffs."""
    _require_tenant_admin(context)

    async with transactional(session):
        connection = await _load_connection_for_update(
            session,
            context=context,
            connection_id=connection_id,
        )
        _validate_expected_version(connection, expected_version)

        if connection.status is not HrisConnectionStatus.ACTIVE:
            raise HrisConnectionValidationError(
                "Only active HRIS connections can be disabled."
            )

        connection.status = HrisConnectionStatus.DISABLED
        connection.disabled_at = datetime.now(UTC)
        connection.disabled_by_subject = context.subject

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="hris_connection.disabled",
            entity_type="hris_connection",
            entity_id=str(connection.id),
            details={
                "status": connection.status.value,
                "version": connection.version,
            },
        )
        await session.flush()

    return await _reload_detached_connection(
        session,
        connection_id=connection_id,
    )


async def delete_hris_connection(
    session: AsyncSession,
    *,
    context: TenantContext,
    connection_id: UUID,
    expected_version: int,
) -> HrisConnection:
    """
    Logically delete a disabled connection.

    The Infisical secret is deliberately retained for the configured retention
    period. A future privileged purge workflow may remove it after confirming
    no retryable handoff or audit-retention obligation remains.
    """
    _require_tenant_admin(context)

    async with transactional(session):
        connection = await _load_connection_for_update(
            session,
            context=context,
            connection_id=connection_id,
        )
        _validate_expected_version(connection, expected_version)

        if connection.status is not HrisConnectionStatus.DISABLED:
            raise HrisConnectionValidationError(
                "An HRIS connection must be disabled before deletion."
            )

        connection.deleted_at = datetime.now(UTC)
        connection.deleted_by_subject = context.subject

        await session.flush()

        record_audit_event(
            session,
            context=context,
            action="hris_connection.deleted",
            entity_type="hris_connection",
            entity_id=str(connection.id),
            details={
                "status": connection.status.value,
                "version": connection.version,
            },
        )
        await session.flush()

    return await _reload_detached_connection(
        session,
        connection_id=connection_id,
    )
