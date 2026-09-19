"""HTTP integration tests for private webhook management endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_db_session,
    get_tenant_context,
    get_webhook_signing_secret_vault,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant
from app.main import create_app

_ALLOWED_HOST = "hooks.partner.example.test"


@dataclass
class FakeWebhookSigningSecretVault:
    """In-memory vault double that never exposes secret values to the API."""

    stored: dict[str, str] = field(default_factory=dict)
    deleted_references: list[str] = field(default_factory=list)

    async def store_webhook_signing_secret(
        self,
        *,
        secret: SecretStr,
    ) -> str:
        """Store a generated secret under an opaque test reference."""
        reference = f"tap-webhook-{uuid4().hex}"
        self.stored[reference] = secret.get_secret_value()
        return reference

    async def delete_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> None:
        """Record vault cleanup without leaking secret content."""
        self.deleted_references.append(secret_reference)
        self.stored.pop(secret_reference, None)


def _settings() -> Settings:
    """Build isolated settings without loading local developer configuration."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
        webhook_allowed_hosts=[_ALLOWED_HOST],
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _context_dependency(
    tenant_id: UUID,
    *,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Build one verified tenant context override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="webhook-api-admin",
            roles=roles,
            request_id="webhook-api-test-request",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide request-scoped sessions using the isolated PostgreSQL database."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async def override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    return override


async def _public_host_resolver(_: str) -> tuple[str, ...]:
    """Return a deterministic public address without network access."""
    return ("8.8.8.8",)


async def _private_host_resolver(_: str) -> tuple[str, ...]:
    """Return a private address to verify SSRF rejection."""
    return ("127.0.0.1",)


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    roles: frozenset[Role],
) -> None:
    """Switch the simulated verified caller for subsequent requests."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles=roles,
    )


def _headers() -> dict[str, str]:
    """Return one unique idempotency key."""
    return {"Idempotency-Key": str(uuid4())}


def _payload() -> dict[str, object]:
    """Return a valid endpoint creation request."""
    return {
        "name": "Partner HRIS",
        "url": f"https://{_ALLOWED_HOST}/events",
        "event_types": ["application.hired", "offer.accepted"],
    }


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one tenant required by webhook foreign keys."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Webhook API Tenant {tenant_id.hex[:12]}",
                slug=f"webhook-api-{tenant_id.hex[:12]}",
            )
        )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="webhook_vault")
def webhook_vault_fixture() -> FakeWebhookSigningSecretVault:
    """Provide an isolated external-secret substitute."""
    return FakeWebhookSigningSecretVault()


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
    webhook_vault: FakeWebhookSigningSecretVault,
) -> AsyncIterator[FastAPI]:
    """Create a private API application with safe dependency overrides."""
    application = create_app(_settings())
    application.state.webhook_host_resolver = _public_host_resolver

    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.dependency_overrides[
        get_webhook_signing_secret_vault
    ] = lambda: webhook_vault

    _set_context(
        application,
        tenant_id=tenant_id,
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    yield application

    application.dependency_overrides.clear()

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, idempotency_records, webhook_deliveries, "
                "webhook_events, webhook_subscriptions, webhook_endpoints, "
                "tenants CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_creates_endpoint_and_replays_without_exposing_secret(
    api_app: FastAPI,
    webhook_vault: FakeWebhookSigningSecretVault,
) -> None:
    """Creation is replay-safe and never returns vault references or secrets."""
    headers = _headers()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=headers,
        )
        replay = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=headers,
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json() == replay.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"

    body = first.json()
    assert body["status"] == "active"
    assert body["event_types"] == ["application.hired", "offer.accepted"]
    assert "credential_reference" not in body
    assert "secret" not in str(body).lower()
    assert len(webhook_vault.stored) == 1


@pytest.mark.asyncio
async def test_requires_tenant_admin_and_uses_private_response(
    api_app: FastAPI,
    tenant_id: UUID,
) -> None:
    """Recruiters cannot configure external outbound integrations."""
    _set_context(
        api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_hides_other_tenant_endpoint(
    api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """An endpoint in another tenant is indistinguishable from missing."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=_headers(),
        )

        other_tenant_id = uuid4()
        await _create_tenant(database_engine, other_tenant_id)
        _set_context(
            api_app,
            tenant_id=other_tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )

        hidden = await client.get(
            f"/api/v1/webhook-endpoints/{created.json()['id']}"
        )
        listed = await client.get("/api/v1/webhook-endpoints")

    assert created.status_code == 201
    assert hidden.status_code == 404
    assert hidden.headers["Cache-Control"] == "private, no-store"
    assert listed.status_code == 200
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_rejects_unknown_fields_and_ssrf_destinations(
    api_app: FastAPI,
) -> None:
    """Strict request schemas and DNS-level SSRF controls both apply."""
    invalid_payload = {
        **_payload(),
        "unexpected_field": "must fail",
    }

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        strict_fields = await client.post(
            "/api/v1/webhook-endpoints",
            json=invalid_payload,
            headers=_headers(),
        )

        api_app.state.webhook_host_resolver = _private_host_resolver
        ssrf = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=_headers(),
        )

    assert strict_fields.status_code == 422
    assert ssrf.status_code == 422
    assert ssrf.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_updates_rotates_disables_and_logically_deletes_endpoint(
    api_app: FastAPI,
    webhook_vault: FakeWebhookSigningSecretVault,
) -> None:
    """Lifecycle writes use versions, idempotency, and private responses."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/webhook-endpoints",
            json=_payload(),
            headers=_headers(),
        )
        endpoint = created.json()
        endpoint_id = endpoint["id"]

        updated = await client.put(
            f"/api/v1/webhook-endpoints/{endpoint_id}",
            json={
                "name": "Updated Partner HRIS",
                "url": f"https://{_ALLOWED_HOST}/updated-events",
                "event_types": ["application.hired"],
                "expected_version": endpoint["version"],
            },
            headers=_headers(),
        )

        rotated = await client.post(
            f"/api/v1/webhook-endpoints/{endpoint_id}/secret-rotations",
            json={"expected_version": updated.json()["version"]},
            headers=_headers(),
        )

        stale = await client.post(
            f"/api/v1/webhook-endpoints/{endpoint_id}/disable",
            json={"expected_version": updated.json()["version"]},
            headers=_headers(),
        )

        disabled = await client.post(
            f"/api/v1/webhook-endpoints/{endpoint_id}/disable",
            json={"expected_version": rotated.json()["version"]},
            headers=_headers(),
        )

        deleted = await client.request(
            "DELETE",
            f"/api/v1/webhook-endpoints/{endpoint_id}",
            json={"expected_version": disabled.json()["version"]},
            headers=_headers(),
        )

        current = await client.get(
            f"/api/v1/webhook-endpoints/{endpoint_id}"
        )

    assert created.status_code == 201
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated Partner HRIS"
    assert updated.json()["event_types"] == ["application.hired"]

    assert rotated.status_code == 200
    assert "credential_reference" not in rotated.json()
    assert len(webhook_vault.deleted_references) >= 1

    assert stale.status_code == 409
    assert stale.headers["Cache-Control"] == "private, no-store"

    assert disabled.status_code == 200
    assert disabled.json()["status"] == "disabled"

    assert deleted.status_code == 200
    assert deleted.json() == {
        "id": endpoint_id,
        "status": "deleted",
    }
    assert deleted.headers["Cache-Control"] == "private, no-store"

    assert current.status_code == 200
    assert current.json()["status"] == "disabled"
    assert "credential_reference" not in current.json()
