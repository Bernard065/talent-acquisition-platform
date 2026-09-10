"""HTTP integration tests for private notification preference endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant, User
from app.domains.notifications.enums import (
    NotificationChannel,
    NotificationEventType,
)
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated API settings without loading local environment values."""
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
    subject: str,
) -> Callable[[], Awaitable[TenantContext]]:
    """Build a verified caller identity dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject=subject,
            roles=frozenset({Role.RECRUITER}),
            request_id="notification-preferences-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build request-scoped sessions against the isolated test database."""
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


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    subject: str = "notification-user-subject",
) -> None:
    """Set the verified caller for the following request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject=subject,
    )


def _headers() -> dict[str, str]:
    """Return a unique idempotency key for one preference mutation."""
    return {"Idempotency-Key": str(uuid4())}


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create one tenant required by tenant-owned user records."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Notification API Tenant {tenant_id.hex[:12]}",
                slug=f"notification-api-{tenant_id.hex[:12]}",
            )
        )


async def _create_user(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    subject: str = "notification-user-subject",
) -> User:
    """Create the internal tenant user represented by the test JWT subject."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        user = User(
            tenant_id=tenant_id,
            external_subject=subject,
            email=f"notifications-{tenant_id.hex[:12]}@example.test",
            display_name="Notification User",
        )
        session.add(user)
        await session.flush()
        return user


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant used by the default API caller."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create an API app using test database and identity overrides."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    _set_context(application, tenant_id=tenant_id)

    yield application

    application.dependency_overrides.clear()

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_lists_enabled_defaults_with_private_no_store_response(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Unpersisted preferences must appear as enabled version-zero defaults."""
    await _create_user(database_engine, tenant_id=tenant_id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/notification-preferences")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"

    preferences = response.json()
    assert len(preferences) == (
        len(NotificationEventType) * len(NotificationChannel)
    )
    assert all(item["enabled"] is True for item in preferences)
    assert all(item["version"] == 0 for item in preferences)
    assert {
        item["event_type"] for item in preferences
    } == {event_type.value for event_type in NotificationEventType}


@pytest.mark.asyncio
async def test_updates_preference_and_replays_idempotently(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one opt-out exactly once and replay the stored response."""
    await _create_user(database_engine, tenant_id=tenant_id)
    headers = _headers()
    payload = {"enabled": False, "expected_version": 0}

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json=payload,
            headers=headers,
        )
        replay = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json=payload,
            headers=headers,
        )
        listed = await client.get("/api/v1/notification-preferences")

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert first.headers["Cache-Control"] == "private, no-store"
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.json()["enabled"] is False
    assert first.json()["version"] == 1

    offer_sent = next(
        item
        for item in listed.json()
        if item["event_type"] == "offer.sent"
        and item["channel"] == "email"
    )
    assert offer_sent["enabled"] is False
    assert offer_sent["version"] == 1


@pytest.mark.asyncio
async def test_rejects_stale_preference_version(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Require a fresh version for a non-idempotent preference update."""
    await _create_user(database_engine, tenant_id=tenant_id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json={"enabled": False, "expected_version": 0},
            headers=_headers(),
        )
        stale = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json={"enabled": True, "expected_version": 0},
            headers=_headers(),
        )

    assert first.status_code == 200
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_tenant_context_keeps_preferences_isolated(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """The same subject in another tenant receives independent preferences."""
    await _create_user(database_engine, tenant_id=tenant_id)

    other_tenant_id = uuid4()
    await _create_tenant(database_engine, other_tenant_id)
    await _create_user(database_engine, tenant_id=other_tenant_id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        owner_update = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json={"enabled": False, "expected_version": 0},
            headers=_headers(),
        )

        _set_context(api_app, tenant_id=other_tenant_id)
        other_list = await client.get("/api/v1/notification-preferences")

        _set_context(api_app, tenant_id=tenant_id)
        owner_list = await client.get("/api/v1/notification-preferences")

    other_offer_sent = next(
        item
        for item in other_list.json()
        if item["event_type"] == "offer.sent"
        and item["channel"] == "email"
    )
    owner_offer_sent = next(
        item
        for item in owner_list.json()
        if item["event_type"] == "offer.sent"
        and item["channel"] == "email"
    )

    assert owner_update.status_code == 200
    assert other_offer_sent["enabled"] is True
    assert other_offer_sent["version"] == 0
    assert owner_offer_sent["enabled"] is False
    assert owner_offer_sent["version"] == 1


@pytest.mark.asyncio
async def test_rejects_unknown_fields_and_missing_internal_user(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Strict contracts and self-service identity boundaries are enforced."""
    await _create_user(database_engine, tenant_id=tenant_id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        strict_fields = await client.put(
            "/api/v1/notification-preferences/offer.sent/email",
            json={
                "enabled": False,
                "expected_version": 0,
                "unexpected_field": "must fail",
            },
            headers=_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="unknown-subject",
        )
        missing_user = await client.get("/api/v1/notification-preferences")

    assert strict_fields.status_code == 422
    assert missing_user.status_code == 403
