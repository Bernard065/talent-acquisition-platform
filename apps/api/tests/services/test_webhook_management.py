"""Unit and PostgreSQL integration tests for secure webhook management."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NoReturn
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import Role, TenantContext
from app.db.models.audit import AuditEvent
from app.db.models.identity import Tenant
from app.db.models.webhook import WebhookEndpoint, WebhookSubscription
from app.domains.webhooks.enums import WebhookEndpointStatus
from app.services import webhook_management
from app.services.webhook_management import (
    CreateWebhookEndpointCommand,
    create_webhook_endpoint,
    disable_webhook_endpoint,
    validate_webhook_destination,
)
from app.services.webhook_management_errors import (
    WebhookAccessDeniedError,
    WebhookEndpointNotFoundError,
    WebhookValidationError,
    WebhookVersionConflictError,
)
from app.services.webhook_secrets import WebhookSigningSecretVaultError

_ALLOWED_HOSTS = ("hooks.partner.example.test", ".webhooks.partner.example.test")
_PUBLIC_ADDRESS = ("8.8.8.8",)


@dataclass
class _FakeWebhookSigningSecretVault:
    """In-memory external-vault substitute that never persists to PostgreSQL."""

    stored: dict[str, str] = field(default_factory=dict)
    deleted_references: list[str] = field(default_factory=list)
    store_error: WebhookSigningSecretVaultError | None = None

    async def store_webhook_signing_secret(self, *, secret: SecretStr) -> str:
        """Store one test secret and return an opaque reference."""
        if self.store_error is not None:
            raise self.store_error

        reference = f"tap-webhook-{uuid4().hex}"
        self.stored[reference] = secret.get_secret_value()
        return reference

    async def delete_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> None:
        """Record compensating cleanup."""
        self.deleted_references.append(secret_reference)
        self.stored.pop(secret_reference, None)


async def _public_resolver(_: str) -> tuple[str, ...]:
    """Resolve a test hostname to a public documentation address."""
    return _PUBLIC_ADDRESS


def _context(
    tenant_id: UUID,
    *,
    roles: frozenset[Role] | None = None,
    subject: str = "tenant-admin-subject",
) -> TenantContext:
    """Build a verified caller context for webhook tests."""
    return TenantContext(
        tenant_id=tenant_id,
        subject=subject,
        roles=roles or frozenset({Role.TENANT_ADMIN}),
        request_id="webhook-management-test-request",
    )


async def _seed_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Persist the tenant required by webhook foreign keys."""
    session.add(
        Tenant(
            id=tenant_id,
            name=f"Webhook Tenant {tenant_id.hex[:12]}",
            slug=f"webhook-{tenant_id.hex[:12]}",
        )
    )
    await session.commit()


def _command(
    *,
    name: str = "Partner HRIS",
    url: str = "https://hooks.partner.example.test/tap",
    event_types: tuple[str, ...] = ("application.hired",),
) -> CreateWebhookEndpointCommand:
    """Return a representative safe endpoint command."""
    return CreateWebhookEndpointCommand(
        name=name,
        url=url,
        event_types=event_types,
    )


@pytest.mark.asyncio
async def test_rejects_non_admin_before_secret_creation(
    session: AsyncSession,
) -> None:
    """Only tenant administrators may configure outbound integrations."""
    tenant_id = uuid4()
    vault = _FakeWebhookSigningSecretVault()

    with pytest.raises(WebhookAccessDeniedError):
        await create_webhook_endpoint(
            session,
            context=_context(
                tenant_id,
                roles=frozenset({Role.RECRUITER}),
            ),
            command=_command(),
            signing_secret_vault=vault,
            allowed_hosts=_ALLOWED_HOSTS,
            host_resolver=_public_resolver,
        )

    assert not vault.stored


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "addresses"),
    [
        ("http://hooks.partner.example.test/tap", _PUBLIC_ADDRESS),
        ("https://127.0.0.1/tap", _PUBLIC_ADDRESS),
        ("https://hooks.partner.example.test:444/tap", _PUBLIC_ADDRESS),
        ("https://hooks.partner.example.test/tap?token=secret", _PUBLIC_ADDRESS),
        ("https://user@hooks.partner.example.test/tap", _PUBLIC_ADDRESS),
        ("https://untrusted.example.test/tap", _PUBLIC_ADDRESS),
        ("https://hooks.partner.example.test/tap", ("127.0.0.1",)),
        ("https://hooks.partner.example.test/tap", ("169.254.169.254",)),
    ],
)
async def test_rejects_ssrf_and_unsafe_destinations(
    url: str,
    addresses: tuple[str, ...],
) -> None:
    """Reject non-HTTPS, credential-bearing, untrusted, and private targets."""

    async def resolver(_: str) -> tuple[str, ...]:
        return addresses

    with pytest.raises(WebhookValidationError):
        await validate_webhook_destination(
            url=url,
            allowed_hosts=_ALLOWED_HOSTS,
            host_resolver=resolver,
        )


@pytest.mark.asyncio
async def test_accepts_allowlisted_public_subdomain() -> None:
    """Explicit suffix allow-list entries permit only their subdomains."""
    destination = await validate_webhook_destination(
        url="https://events.webhooks.partner.example.test/callback",
        allowed_hosts=_ALLOWED_HOSTS,
        host_resolver=_public_resolver,
    )

    assert destination == "https://events.webhooks.partner.example.test/callback"


@pytest.mark.asyncio
async def test_creates_unique_normalized_subscriptions_and_private_audit(
    session: AsyncSession,
) -> None:
    """Duplicate input event types create one subscription and safe audit data."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    vault = _FakeWebhookSigningSecretVault()
    endpoint = await create_webhook_endpoint(
        session,
        context=_context(tenant_id),
        command=_command(
            event_types=(
                "application.hired",
                "application.hired",
                "offer.accepted",
            )
        ),
        signing_secret_vault=vault,
        allowed_hosts=_ALLOWED_HOSTS,
        host_resolver=_public_resolver,
    )

    subscriptions = list(
        await session.scalars(
            select(WebhookSubscription)
            .where(WebhookSubscription.webhook_endpoint_id == endpoint.id)
            .order_by(WebhookSubscription.event_type)
        )
    )
    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "webhook_endpoint.created",
            AuditEvent.entity_id == str(endpoint.id),
        )
    )

    assert [subscription.event_type for subscription in subscriptions] == [
        "application.hired",
        "offer.accepted",
    ]
    assert audit is not None
    assert audit.details == {
        "subscription_count": 2,
        "status": "active",
        "version": 1,
    }

    rendered_audit = str(audit.details)
    secret_value = next(iter(vault.stored.values()))
    for prohibited_value in (
        endpoint.url,
        endpoint.credential_reference,
        secret_value,
        "application.hired",
        "offer.accepted",
    ):
        assert prohibited_value not in rendered_audit


@pytest.mark.asyncio
async def test_database_enforces_subscription_uniqueness(
    session: AsyncSession,
) -> None:
    """The unique constraint prevents duplicate rows outside the service."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    endpoint = await create_webhook_endpoint(
        session,
        context=_context(tenant_id),
        command=_command(),
        signing_secret_vault=_FakeWebhookSigningSecretVault(),
        allowed_hosts=_ALLOWED_HOSTS,
        host_resolver=_public_resolver,
    )

    session.add(
        WebhookSubscription(
            tenant_id=tenant_id,
            webhook_endpoint_id=endpoint.id,
            event_type="application.hired",
        )
    )

    with pytest.raises(IntegrityError):
        await session.commit()

    await session.rollback()


@pytest.mark.asyncio
async def test_tenant_cannot_disable_another_tenants_endpoint(
    session: AsyncSession,
) -> None:
    """Cross-tenant endpoint access is indistinguishable from absence."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    await _seed_tenant(session, owner_tenant_id)
    await _seed_tenant(session, other_tenant_id)

    endpoint = await create_webhook_endpoint(
        session,
        context=_context(owner_tenant_id),
        command=_command(),
        signing_secret_vault=_FakeWebhookSigningSecretVault(),
        allowed_hosts=_ALLOWED_HOSTS,
        host_resolver=_public_resolver,
    )
    endpoint_id = endpoint.id

    with pytest.raises(WebhookEndpointNotFoundError):
        await disable_webhook_endpoint(
            session,
            context=_context(other_tenant_id),
            webhook_endpoint_id=endpoint_id,
            expected_version=endpoint.version,
        )

    persisted = await session.get(WebhookEndpoint, endpoint_id)
    assert persisted is not None
    assert persisted.status is WebhookEndpointStatus.ACTIVE


@pytest.mark.asyncio
async def test_disable_requires_current_version_and_records_safe_audit(
    session: AsyncSession,
) -> None:
    """Endpoint updates use optimistic concurrency and leave an audit trail."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)
    context = _context(tenant_id)

    endpoint = await create_webhook_endpoint(
        session,
        context=context,
        command=_command(),
        signing_secret_vault=_FakeWebhookSigningSecretVault(),
        allowed_hosts=_ALLOWED_HOSTS,
        host_resolver=_public_resolver,
    )
    endpoint_id = endpoint.id
    initial_version = endpoint.version

    disabled = await disable_webhook_endpoint(
        session,
        context=context,
        webhook_endpoint_id=endpoint_id,
        expected_version=initial_version,
    )
    disabled_status = disabled.status
    disabled_version = disabled.version

    with pytest.raises(WebhookVersionConflictError):
        await disable_webhook_endpoint(
            session,
            context=context,
            webhook_endpoint_id=endpoint_id,
            expected_version=initial_version,
        )

    audit = await session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "webhook_endpoint.disabled",
            AuditEvent.entity_id == str(endpoint_id),
        )
    )

    assert disabled_status is WebhookEndpointStatus.DISABLED
    assert disabled_version == initial_version + 1
    assert audit is not None
    assert audit.details == {
        "status": "disabled",
        "version": disabled_version,
    }


@pytest.mark.asyncio
async def test_deletes_secret_when_database_transaction_fails(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compensate for external secret creation when database work rolls back."""
    tenant_id = uuid4()
    await _seed_tenant(session, tenant_id)

    vault = _FakeWebhookSigningSecretVault()

    def fail_audit(*_: object, **__: object) -> NoReturn:
        raise RuntimeError("simulated database persistence failure")

    monkeypatch.setattr(webhook_management, "record_audit_event", fail_audit)

    with pytest.raises(RuntimeError, match="simulated database persistence failure"):
        await create_webhook_endpoint(
            session,
            context=_context(tenant_id),
            command=_command(),
            signing_secret_vault=vault,
            allowed_hosts=_ALLOWED_HOSTS,
            host_resolver=_public_resolver,
        )

    endpoints = list(
        await session.scalars(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id
            )
        )
    )

    assert not endpoints
    assert not vault.stored
    assert len(vault.deleted_references) == 1
