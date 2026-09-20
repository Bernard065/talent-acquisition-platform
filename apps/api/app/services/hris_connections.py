"""Tenant-admin HRIS connection configuration service."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.hris import HrisConnection
from app.db.models.identity import Tenant
from app.db.transactions import transactional
from app.domains.hris.enums import HrisConnectionStatus, HrisProvider
from app.services.audit import record_audit_event
from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVault,
    HrisCredentialVaultError,
)
from app.services.hris_errors import (
    HrisAccessDeniedError,
    HrisActiveConnectionExistsError,
    HrisConnectionAlreadyExistsError,
    HrisConnectionValidationError,
    HrisCredentialStorageError,
)

_MAX_CONNECTION_NAME_LENGTH = 100


@dataclass(frozen=True, slots=True)
class CreateHrisConnectionCommand:
    """Input required to create one active tenant HRIS connection."""

    name: str
    provider: HrisProvider
    credentials: HrisCredentials

    def __post_init__(self) -> None:
        normalized_name = self.name.strip()

        if not normalized_name or len(normalized_name) > _MAX_CONNECTION_NAME_LENGTH:
            raise HrisConnectionValidationError(
                "HRIS connection name is invalid."
            )

        object.__setattr__(self, "name", normalized_name)


def _require_tenant_admin(context: TenantContext) -> None:
    """Restrict HRIS configuration to tenant administrators."""
    if Role.TENANT_ADMIN not in context.roles:
        raise HrisAccessDeniedError(
            "Tenant administrator permission is required for HRIS configuration."
        )


async def create_hris_connection(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateHrisConnectionCommand,
    credential_vault: HrisCredentialVault,
) -> HrisConnection:
    """
    Create the tenant's one active HRIS handoff destination.

    The secret is persisted first. If the database transaction fails, the
    service compensates by deleting the newly created external secret.
    """

    _require_tenant_admin(context)

    try:
        credential_reference = await credential_vault.store_hris_credentials(
            provider=command.provider.value,
            tenant_id=str(context.tenant_id),
            credentials=command.credentials,
        )
    except HrisCredentialVaultError as error:
        raise HrisCredentialStorageError(
            error.code,
            retryable=error.retryable,
        ) from error

    if not credential_reference or len(credential_reference) > 500:
        raise HrisCredentialStorageError(
            "hris_credential_reference_invalid",
            retryable=False,
        )

    try:
        async with transactional(session):
            # Serializes active-connection configuration within one tenant.
            tenant = await session.scalar(
                select(Tenant)
                .where(Tenant.id == context.tenant_id)
                .with_for_update()
            )
            if tenant is None:
                raise HrisAccessDeniedError(
                    "Tenant is not available for HRIS configuration."
                )

            active_connection = await session.scalar(
                select(HrisConnection.id).where(
                    HrisConnection.tenant_id == context.tenant_id,
                    HrisConnection.status == HrisConnectionStatus.ACTIVE,
                    HrisConnection.deleted_at.is_(None),
                )
            )
            if active_connection is not None:
                raise HrisActiveConnectionExistsError(
                    "Only one active HRIS connection is supported per tenant."
                )

            existing_connection = await session.scalar(
                select(HrisConnection.id).where(
                    HrisConnection.tenant_id == context.tenant_id,
                    HrisConnection.provider == command.provider,
                    HrisConnection.name == command.name,
                    HrisConnection.deleted_at.is_(None),
                )
            )
            if existing_connection is not None:
                raise HrisConnectionAlreadyExistsError(
                    "An HRIS connection with this provider and name exists."
                )

            connection = HrisConnection(
                tenant_id=context.tenant_id,
                name=command.name,
                provider=command.provider,
                status=HrisConnectionStatus.ACTIVE,
                credential_reference=credential_reference,
                created_by_subject=context.subject,
            )
            session.add(connection)
            await session.flush()

            record_audit_event(
                session,
                context=context,
                action="hris_connection.created",
                entity_type="hris_connection",
                entity_id=str(connection.id),
                details={
                    "provider": connection.provider.value,
                    "status": connection.status.value,
                    "version": connection.version,
                },
            )
            await session.flush()
            await session.refresh(connection)

    except IntegrityError as error:
        with suppress(HrisCredentialVaultError):
            await credential_vault.delete_hris_credentials(
                credential_reference=credential_reference,
            )
        raise HrisConnectionAlreadyExistsError(
            "An HRIS connection with this provider and name exists."
        ) from error
    except Exception:
        with suppress(HrisCredentialVaultError):
            await credential_vault.delete_hris_credentials(
                credential_reference=credential_reference,
            )
        raise

    return connection
