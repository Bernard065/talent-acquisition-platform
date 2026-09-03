"""HTTP integration tests for requisition endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant
from app.main import create_app


def _test_settings() -> Settings:
    """Build settings without requiring a local .env file."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
        jwt_issuer=AnyHttpUrl("https://issuer.example.test/"),
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url=AnyHttpUrl(
            "https://issuer.example.test/.well-known/jwks.json"
        ),
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _context_dependency(
    tenant_id: UUID,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return a dependency that represents an already verified caller."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=roles,
            request_id="test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped database session dependency for ASGI tests."""
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


@pytest_asyncio.fixture(name="test_tenant_id")
async def _test_tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create one tenant used by the verified caller in each test."""
    value = uuid4()
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=value,
                name="Test Tenant",
                slug=f"test-tenant-{value.hex[:12]}",
            )
        )

    return value


@pytest_asyncio.fixture(name="requisition_app")
async def _requisition_app_fixture(
    database_engine: AsyncEngine,
    test_tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create an application with auth and database dependencies overridden."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        test_tenant_id,
        frozenset({Role.RECRUITER}),
    )
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )

    yield application

    application.dependency_overrides.clear()


async def _create_requisition(
    client: AsyncClient,
    *,
    title: str,
) -> dict[str, object]:
    """Create a requisition through the public HTTP API."""
    response = await client.post(
        "/api/v1/requisitions",
        json={
            "title": title,
            "department": "Engineering",
            "headcount": 1,
        },
    )

    assert response.status_code == 201
    return cast(dict[str, object], response.json())


@pytest.mark.asyncio
async def test_creates_and_gets_requisition(
    requisition_app: FastAPI,
) -> None:
    """Create a requisition and retrieve it through the HTTP API."""
    transport = ASGITransport(app=requisition_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        created = await _create_requisition(
            client,
            title="Senior Backend Engineer",
        )
        response = await client.get(f"/api/v1/requisitions/{created['id']}")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in response.headers
    assert response.json()["id"] == created["id"]
    assert response.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_lists_requisitions_with_cursor_pagination(
    requisition_app: FastAPI,
) -> None:
    """List requisitions across multiple cursor-paginated responses."""
    transport = ASGITransport(app=requisition_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        created = [
            await _create_requisition(client, title=title)
            for title in (
                "Backend Engineer",
                "Frontend Engineer",
                "Product Designer",
            )
        ]

        first_page = await client.get("/api/v1/requisitions?limit=2")
        cursor = first_page.json()["next_cursor"]
        second_page = await client.get(
            "/api/v1/requisitions",
            params={"limit": 2, "cursor": cursor},
        )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    returned_ids = {
        item["id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    }
    assert returned_ids == {item["id"] for item in created}


@pytest.mark.asyncio
async def test_updates_draft_then_rejects_update_after_transition(
    requisition_app: FastAPI,
) -> None:
    """Allow draft updates but reject updates after a state transition."""
    transport = ASGITransport(app=requisition_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        created = await _create_requisition(
            client,
            title="Backend Engineer",
        )

        updated = await client.patch(
            f"/api/v1/requisitions/{created['id']}",
            json={
                "location": "Nairobi",
                "headcount": 2,
            },
        )
        transitioned = await client.post(
            f"/api/v1/requisitions/{created['id']}/transitions",
            json={"target_status": "pending_approval"},
        )
        rejected_update = await client.patch(
            f"/api/v1/requisitions/{created['id']}",
            json={"title": "Principal Backend Engineer"},
        )

    assert updated.status_code == 200
    assert updated.json()["location"] == "Nairobi"
    assert updated.json()["version"] == 2

    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "pending_approval"

    assert rejected_update.status_code == 409
    assert rejected_update.json()["detail"] == (
        "The requisition cannot be changed in its current state."
    )


@pytest.mark.asyncio
async def test_hides_requisition_from_another_tenant(
    requisition_app: FastAPI,
) -> None:
    """Prevent a caller from accessing another tenant's requisition."""
    transport = ASGITransport(app=requisition_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        created = await _create_requisition(
            client,
            title="Backend Engineer",
        )

        requisition_app.dependency_overrides[get_tenant_context] = (
            _context_dependency(
                uuid4(),
                frozenset({Role.RECRUITER}),
            )
        )

        response = await client.get(
            f"/api/v1/requisitions/{created['id']}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Requisition not found."


@pytest.mark.asyncio
async def test_rejects_write_for_read_only_role(
    requisition_app: FastAPI,
    test_tenant_id: UUID,
) -> None:
    """Reject requisition creation for a read-only tenant role."""
    requisition_app.dependency_overrides[get_tenant_context] = (
        _context_dependency(
            test_tenant_id,
            frozenset({Role.ANALYST}),
        )
    )

    transport = ASGITransport(app=requisition_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/requisitions",
            json={"title": "Backend Engineer"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."
