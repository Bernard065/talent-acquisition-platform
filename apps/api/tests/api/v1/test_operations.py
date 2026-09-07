"""HTTP integration tests for tenant dead-letter operations."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
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
from app.db.models.identity import Tenant
from app.db.models.outbox import OutboxEvent
from app.domains.outbox.enums import OutboxEventStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without loading local environment configuration."""
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
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return an already verified identity for one test request."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="tenant-admin-subject",
            roles=roles,
            request_id="operations-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped async database session."""

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
    roles: frozenset[Role],
) -> None:
    """Change the verified caller for the next request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one tenant required by the outbox foreign key."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Operations Tenant {tenant_id.hex[:12]}",
                slug=f"operations-{tenant_id.hex[:12]}",
            )
        )


async def _create_dead_letter(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    position: int,
    dead_lettered_at: datetime,
) -> OutboxEvent:
    """Seed one dead-letter record containing deliberately private payload data."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        event = OutboxEvent(
            tenant_id=tenant_id,
            event_type="candidate_document.scan_requested",
            aggregate_type="candidate_document",
            aggregate_id=str(uuid4()),
            deduplication_key=f"operations-event-{tenant_id}-{position}",
            payload={
                "document_id": "private-document-id",
                "storage_key": "private-storage-key",
                "email": "private@example.test",
            },
            status=OutboxEventStatus.DEAD_LETTERED,
            attempts=3,
            dead_lettered_at=dead_lettered_at,
            last_error="malware_scanner_unavailable",
        )
        session.add(event)
        await session.flush()
        return event


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant used by the default API caller."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="operations_app")
async def operations_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create an app with database and verified-identity dependencies overridden."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
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
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )


@pytest.mark.asyncio
async def test_requires_tenant_admin(
    operations_app: FastAPI,
    tenant_id: UUID,
) -> None:
    """Reject dead-letter inspection by non-administrator roles."""
    _set_context(
        operations_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=operations_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/operations/outbox/dead-letters")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_returns_only_safe_dead_letters_from_callers_tenant(
    operations_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Preserve tenant isolation and exclude payload data from API responses."""
    now = datetime.now(UTC)
    owned_event = await _create_dead_letter(
        database_engine,
        tenant_id=tenant_id,
        position=1,
        dead_lettered_at=now,
    )

    other_tenant_id = uuid4()
    await _create_tenant(database_engine, other_tenant_id)
    await _create_dead_letter(
        database_engine,
        tenant_id=other_tenant_id,
        position=1,
        dead_lettered_at=now + timedelta(seconds=1),
    )

    async with AsyncClient(
        transport=ASGITransport(app=operations_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/operations/outbox/dead-letters")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"

    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [str(owned_event.id)]

    serialized = str(payload)
    assert "payload" not in payload["items"][0]
    assert "private-document-id" not in serialized
    assert "private-storage-key" not in serialized
    assert "private@example.test" not in serialized
    assert "tenant_id" not in payload["items"][0]


@pytest.mark.asyncio
async def test_paginates_dead_letters_without_duplicates(
    operations_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Use stable keyset pagination for tenant-admin operations."""
    now = datetime.now(UTC)
    created = [
        await _create_dead_letter(
            database_engine,
            tenant_id=tenant_id,
            position=position,
            dead_lettered_at=now + timedelta(seconds=position),
        )
        for position in range(3)
    ]

    async with AsyncClient(
        transport=ASGITransport(app=operations_app),
        base_url="http://testserver",
    ) as client:
        first_page = await client.get(
            "/api/v1/operations/outbox/dead-letters",
            params={"limit": 2},
        )
        cursor = first_page.json()["next_cursor"]

        second_page = await client.get(
            "/api/v1/operations/outbox/dead-letters",
            params={"limit": 2, "cursor": cursor},
        )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    returned_ids = [
        item["id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ]

    assert returned_ids == [
        str(created[2].id),
        str(created[1].id),
        str(created[0].id),
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_rejects_invalid_outbox_cursor(
    operations_app: FastAPI,
) -> None:
    """Return a safe validation response for malformed cursors."""
    async with AsyncClient(
        transport=ASGITransport(app=operations_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/operations/outbox/dead-letters",
            params={"cursor": "not-a-valid-cursor"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid outbox cursor."
