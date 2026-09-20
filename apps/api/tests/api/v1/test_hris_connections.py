"""HTTP integration tests for private HRIS connection management."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_db_session,
    get_hris_credential_vault,
    get_tenant_context,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant
from app.main import create_app
from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVaultError,
)


@dataclass
class _FakeHrisCredentialVault:
    """In-memory vault substitute; it never returns credentials to HTTP clients."""

    stored: dict[str, HrisCredentials] = field(default_factory=dict)
    deleted_references: list[str] = field(default_factory=list)
    store_error: HrisCredentialVaultError | None = None

    async def store_hris_credentials(
        self,
        *,
        provider: str,
        tenant_id: str,
        credentials: HrisCredentials,
    ) -> str:
        """Store credentials under an opaque test reference."""
        del provider, tenant_id

        if self.store_error is not None:
            raise self.store_error

        reference = f"tap-hris-{uuid4().hex}"
        self.stored[reference] = credentials
        return reference

    async def resolve_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> HrisCredentials:
        """Resolve a test credential set for protocol completeness."""
        return self.stored[credential_reference]

    async def delete_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> None:
        """Record external-secret cleanup without exposing secret material."""
        self.deleted_references.append(credential_reference)
        self.stored.pop(credential_reference, None)


def _settings() -> Settings:
    """Build isolated API settings without developer environment values."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
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
    """Build a verified tenant-context dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="hris-api-tenant-admin",
            roles=roles,
            request_id="hris-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide isolated request-scoped PostgreSQL sessions."""
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


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one tenant required by HRIS foreign keys."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"HRIS API Tenant {tenant_id.hex[:12]}",
                slug=f"hris-api-{tenant_id.hex[:12]}",
            )
        )


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    roles: frozenset[Role],
) -> None:
    """Switch the simulated verified caller."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles=roles,
    )


def _headers() -> dict[str, str]:
    """Return a new idempotency header."""
    return {"Idempotency-Key": str(uuid4())}


def _payload() -> dict[str, object]:
    """Return valid BambooHR configuration with test-only credentials."""
    return {
        "name": "Primary BambooHR",
        "provider": "bamboohr",
        "credentials": {
            "api_key": "test-api-key",
            "company_domain": "example-company",
        },
    }


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="hris_vault")
def hris_vault_fixture() -> _FakeHrisCredentialVault:
    """Provide an isolated fake HRIS credential vault."""
    return _FakeHrisCredentialVault()


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
    hris_vault: _FakeHrisCredentialVault,
) -> AsyncIterator[FastAPI]:
    """Create a private API app with database and vault overrides."""
    application = create_app(_settings())

    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.dependency_overrides[
        get_hris_credential_vault
    ] = lambda: hris_vault

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
                "audit_events, idempotency_records, hris_handoffs, "
                "hris_connections, tenants CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_tenant_admin_creates_connection_and_replays_safely(
    api_app: FastAPI,
    hris_vault: _FakeHrisCredentialVault,
) -> None:
    """Creation is idempotent and never returns credentials or vault references."""
    headers = _headers()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/hris-connections",
            json=_payload(),
            headers=headers,
        )
        replay = await client.post(
            "/api/v1/hris-connections",
            json=_payload(),
            headers=headers,
        )

    assert created.status_code == 201
    assert replay.status_code == 201
    assert created.json() == replay.json()
    assert created.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert created.headers["Cache-Control"] == "private, no-store"

    body = created.json()
    assert body["name"] == "Primary BambooHR"
    assert body["provider"] == "bamboohr"
    assert body["status"] == "active"
    assert body["disabled_at"] is None
    assert "credential_reference" not in body
    assert "api_key" not in str(body).lower()
    assert "test-api-key" not in str(body)
    assert len(hris_vault.stored) == 1


@pytest.mark.asyncio
async def test_requires_tenant_admin_for_hris_management(
    api_app: FastAPI,
    tenant_id: UUID,
) -> None:
    """Recruiters cannot configure HRIS connections."""
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
            "/api/v1/hris-connections",
            json=_payload(),
            headers=_headers(),
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_rejects_strict_and_invalid_credential_fields(
    api_app: FastAPI,
) -> None:
    """Schemas reject unknown request fields and unsafe credential names."""
    unknown_field_payload = {
        **_payload(),
        "unexpected_field": "must-fail",
    }
    invalid_credential_payload = {
        **_payload(),
        "credentials": {
            "api-key": "test-api-key",
        },
    }

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        unknown_field = await client.post(
            "/api/v1/hris-connections",
            json=unknown_field_payload,
            headers=_headers(),
        )
        invalid_credential = await client.post(
            "/api/v1/hris-connections",
            json=invalid_credential_payload,
            headers=_headers(),
        )

    assert unknown_field.status_code == 422
    assert invalid_credential.status_code == 422

    # Validation responses must not echo supplied credential values.
    assert "test-api-key" not in unknown_field.text
    assert "test-api-key" not in invalid_credential.text


@pytest.mark.asyncio
async def test_hides_connections_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Cross-tenant resources are indistinguishable from missing resources."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/hris-connections",
            json=_payload(),
            headers=_headers(),
        )
        connection_id = created.json()["id"]

        other_tenant_id = uuid4()
        await _create_tenant(database_engine, other_tenant_id)

        _set_context(
            api_app,
            tenant_id=other_tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )

        hidden = await client.get(
            f"/api/v1/hris-connections/{connection_id}"
        )
        listed = await client.get("/api/v1/hris-connections")

    assert created.status_code == 201
    assert hidden.status_code == 404
    assert hidden.headers["Cache-Control"] == "private, no-store"
    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "private, no-store"
    assert listed.json() == {"items": []}


@pytest.mark.asyncio
async def test_returns_private_service_unavailable_when_vault_fails(
    api_app: FastAPI,
    hris_vault: _FakeHrisCredentialVault,
) -> None:
    """Do not reveal Infisical failures to an HRIS administrator."""
    hris_vault.store_error = HrisCredentialVaultError(
        "vault_internal_detail_must_not_escape",
        retryable=True,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/hris-connections",
            json=_payload(),
            headers=_headers(),
        )

    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["Retry-After"] == "5"
    assert response.json()["detail"] == "HRIS management service is unavailable."
    assert "vault_internal_detail" not in response.text


@pytest.mark.asyncio
async def test_disables_deletes_and_rejects_stale_version(
    api_app: FastAPI,
) -> None:
    """Lifecycle writes are private, idempotent, and version-protected."""
    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            "/api/v1/hris-connections",
            json=_payload(),
            headers=_headers(),
        )
        connection = created.json()
        connection_id = connection["id"]

        disabled = await client.post(
            f"/api/v1/hris-connections/{connection_id}/disable",
            json={"expected_version": connection["version"]},
            headers=_headers(),
        )

        stale = await client.post(
            f"/api/v1/hris-connections/{connection_id}/disable",
            json={"expected_version": connection["version"]},
            headers=_headers(),
        )

        deleted = await client.request(
            "DELETE",
            f"/api/v1/hris-connections/{connection_id}",
            json={"expected_version": disabled.json()["version"]},
            headers=_headers(),
        )

        hidden = await client.get(
            f"/api/v1/hris-connections/{connection_id}"
        )
        listed = await client.get("/api/v1/hris-connections")

    assert created.status_code == 201
    assert disabled.status_code == 200
    assert disabled.headers["Cache-Control"] == "private, no-store"
    assert disabled.json()["status"] == "disabled"
    assert disabled.json()["disabled_at"] is not None

    assert stale.status_code == 409
    assert stale.headers["Cache-Control"] == "private, no-store"

    assert deleted.status_code == 200
    assert deleted.headers["Cache-Control"] == "private, no-store"
    assert deleted.json() == {
        "id": connection_id,
        "status": "deleted",
    }

    assert hidden.status_code == 404
    assert hidden.headers["Cache-Control"] == "private, no-store"
    assert listed.status_code == 200
    assert listed.json() == {"items": []}
