"""Tenant-admin webhook endpoint management with SSRF-safe validation."""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
import socket
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from re import compile as re_compile
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.webhook import (
    WebhookEndpoint,
    WebhookSubscription,
)
from app.db.transactions import transactional
from app.domains.webhooks.enums import WebhookEndpointStatus
from app.services.audit import record_audit_event
from app.services.webhook_management_errors import (
    WebhookAccessDeniedError,
    WebhookEndpointNotFoundError,
    WebhookSecretStorageError,
    WebhookValidationError,
    WebhookVersionConflictError,
)
from app.services.webhook_secrets import (
    WebhookSigningSecretVault,
    WebhookSigningSecretVaultError,
)

_EVENT_TYPE_PATTERN = re_compile(r"^[a-z][a-z0-9_.-]{0,99}$")
_MAX_ENDPOINT_NAME_LENGTH = 100
_MAX_EVENT_TYPES_PER_ENDPOINT = 100
_MAX_DESTINATION_ADDRESSES = 32

HostResolver = Callable[[str], Awaitable[tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class CreateWebhookEndpointCommand:
    """Validated intent to create one tenant webhook endpoint and subscriptions."""

    name: str
    url: str
    event_types: tuple[str, ...]


async def resolve_public_host(hostname: str) -> tuple[str, ...]:
    """
    Resolve a hostname and return every address before accepting an endpoint.

    The delivery worker must repeat this check immediately before connection to
    defend against later DNS rebinding; this protects the creation boundary.
    """
    try:
        records = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise WebhookValidationError(
            "Webhook destination hostname could not be resolved."
        ) from error

    addresses = tuple(
        sorted(
            {
                record[4][0]
                for record in records
                if isinstance(record[4][0], str)
            }
        )
    )

    if not addresses or len(addresses) > _MAX_DESTINATION_ADDRESSES:
        raise WebhookValidationError(
            "Webhook destination hostname resolved to an invalid address set."
        )

    return addresses


def _normalize_allowed_hosts(allowed_hosts: Sequence[str]) -> tuple[str, ...]:
    """Normalize configured host allow-list entries, not caller-controlled data."""
    normalized = tuple(
        sorted(
            {
                host.strip().lower().rstrip(".")
                for host in allowed_hosts
                if host.strip()
            }
        )
    )

    if not normalized:
        raise ValueError("At least one webhook destination host must be configured.")

    return normalized


def _host_is_allowed(*, hostname: str, allowed_hosts: Sequence[str]) -> bool:
    """Match exact hosts or explicitly configured subdomain suffixes."""
    for allowed_host in allowed_hosts:
        if allowed_host.startswith("."):
            suffix = allowed_host[1:]
            if hostname.endswith(f".{suffix}"):
                return True
        elif hostname == allowed_host:
            return True

    return False


def _validate_event_types(event_types: tuple[str, ...]) -> tuple[str, ...]:
    """Return unique, supported event type labels in deterministic order."""
    if not event_types or len(event_types) > _MAX_EVENT_TYPES_PER_ENDPOINT:
        raise WebhookValidationError(
            "Webhook endpoints require a bounded non-empty event subscription list."
        )

    normalized = tuple(sorted({event_type.strip() for event_type in event_types}))

    if not all(_EVENT_TYPE_PATTERN.fullmatch(event_type) for event_type in normalized):
        raise WebhookValidationError("Webhook event type is invalid.")

    return normalized


async def validate_webhook_destination(
    *,
    url: str,
    allowed_hosts: Sequence[str],
    host_resolver: HostResolver,
) -> str:
    """
    Validate a configured HTTPS destination before any secret or DB mutation.

    Userinfo and query strings are rejected because credentials belong in the
    signed request model, not in URLs. Only port 443 is accepted.
    """
    if len(url) > 2048:
        raise WebhookValidationError("Webhook destination URL is too long.")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise WebhookValidationError("Webhook destination URL is invalid.") from error

    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in {None, 443}
    ):
        raise WebhookValidationError("Webhook destination URL is not allowed.")

    normalized_host = hostname.lower().rstrip(".")
    configured_hosts = _normalize_allowed_hosts(allowed_hosts)

    # Endpoints must use DNS names. This avoids ambiguous IP-based allow-listing.
    try:
        ipaddress.ip_address(normalized_host)
    except ValueError:
        pass
    else:
        raise WebhookValidationError("Webhook destination must use an allowed hostname.")

    if not _host_is_allowed(
        hostname=normalized_host,
        allowed_hosts=configured_hosts,
    ):
        raise WebhookValidationError("Webhook destination host is not allowed.")

    addresses = await host_resolver(normalized_host)

    for address in addresses:
        try:
            resolved_address = ipaddress.ip_address(address)
        except ValueError as error:
            raise WebhookValidationError(
                "Webhook destination resolution returned an invalid address."
            ) from error

        if not resolved_address.is_global:
            raise WebhookValidationError(
                "Webhook destination resolved to a non-public address."
            )

    return parsed.geturl()


def _require_tenant_admin(context: TenantContext) -> None:
    """Restrict outbound integrations to the tenant administrator role."""
    if Role.TENANT_ADMIN not in context.roles:
        raise WebhookAccessDeniedError(
            "Tenant administrator permission is required for webhooks."
        )


async def create_webhook_endpoint(
    session: AsyncSession,
    *,
    context: TenantContext,
    command: CreateWebhookEndpointCommand,
    signing_secret_vault: WebhookSigningSecretVault,
    allowed_hosts: Sequence[str],
    host_resolver: HostResolver = resolve_public_host,
) -> WebhookEndpoint:
    """
    Create an endpoint and subscriptions atomically after external secret setup.

    The secret is created only after URL validation. If the database transaction
    fails, best-effort compensation removes the externally stored secret.
    """
    _require_tenant_admin(context)

    name = command.name.strip()
    if not name or len(name) > _MAX_ENDPOINT_NAME_LENGTH:
        raise WebhookValidationError("Webhook endpoint name is invalid.")

    event_types = _validate_event_types(command.event_types)
    destination_url = await validate_webhook_destination(
        url=command.url.strip(),
        allowed_hosts=allowed_hosts,
        host_resolver=host_resolver,
    )

    signing_secret = SecretStr(secrets.token_urlsafe(48))

    try:
        secret_reference = await signing_secret_vault.store_webhook_signing_secret(
            secret=signing_secret,
        )
    except WebhookSigningSecretVaultError as error:
        raise WebhookSecretStorageError(
            error.code,
            retryable=error.retryable,
        ) from error

    if not secret_reference or len(secret_reference) > 500:
        raise WebhookSecretStorageError(
            "webhook_secret_reference_invalid",
            retryable=False,
        )

    try:
        async with transactional(session):
            endpoint = WebhookEndpoint(
                tenant_id=context.tenant_id,
                name=name,
                url=destination_url,
                credential_reference=secret_reference,
                created_by_subject=context.subject,
            )
            session.add(endpoint)
            await session.flush()

            session.add_all(
                [
                    WebhookSubscription(
                        tenant_id=context.tenant_id,
                        webhook_endpoint_id=endpoint.id,
                        event_type=event_type,
                    )
                    for event_type in event_types
                ]
            )
            await session.flush()

            record_audit_event(
                session,
                context=context,
                action="webhook_endpoint.created",
                entity_type="webhook_endpoint",
                entity_id=str(endpoint.id),
                details={
                    "subscription_count": len(event_types),
                    "status": endpoint.status.value,
                    "version": endpoint.version,
                },
            )
            await session.flush()
            await session.refresh(endpoint)

    except Exception:
        with suppress(WebhookSigningSecretVaultError):
            await signing_secret_vault.delete_webhook_signing_secret(
                secret_reference=secret_reference,
            )
        raise

    return endpoint


async def disable_webhook_endpoint(
    session: AsyncSession,
    *,
    context: TenantContext,
    webhook_endpoint_id: UUID,
    expected_version: int,
) -> WebhookEndpoint:
    """Disable a tenant endpoint using optimistic concurrency."""
    _require_tenant_admin(context)

    async with transactional(session):
        endpoint = await session.scalar(
            select(WebhookEndpoint)
            .where(
                WebhookEndpoint.id == webhook_endpoint_id,
                WebhookEndpoint.tenant_id == context.tenant_id,
            )
            .with_for_update()
        )
        if endpoint is None:
            raise WebhookEndpointNotFoundError("Webhook endpoint was not found.")

        if endpoint.version != expected_version:
            raise WebhookVersionConflictError(
                "Webhook endpoint changed; retrieve it and retry."
            )

        if endpoint.status is not WebhookEndpointStatus.DISABLED:
            endpoint.status = WebhookEndpointStatus.DISABLED
            await session.flush()

        record_audit_event(
            session,
            context=context,
            action="webhook_endpoint.disabled",
            entity_type="webhook_endpoint",
            entity_id=str(endpoint.id),
            details={
                "status": endpoint.status.value,
                "version": endpoint.version,
            },
        )
        await session.flush()
        await session.refresh(endpoint)

    return endpoint
