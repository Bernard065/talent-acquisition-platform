"""HTTP integration tests for candidate and application endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
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
from app.db.models.requisition import Requisition
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without relying on a local environment file."""
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
    """Return a verified-caller dependency for one test identity."""

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
    """Return a request-scoped session dependency for ASGI endpoint tests."""
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


def _idempotency_headers() -> dict[str, str]:
    """Return a unique idempotency key for one write request."""
    return {"Idempotency-Key": str(uuid4())}


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    roles: frozenset[Role],
) -> None:
    """Replace the verified caller for a subsequent test request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant required by candidate and requisition foreign keys."""
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
                name="Candidate API Test Tenant",
                slug=f"candidate-api-{value.hex[:12]}",
            )
        )

    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the application with only auth and database access overridden."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    _set_context(
        application,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
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


async def _create_candidate(
    client: AsyncClient,
    *,
    email: str = "ada@acme.io",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create one candidate through the public API."""
    response = await client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "source": "employee_referral",
            "source_metadata": {"campaign": "engineering-q3"},
        },
        headers=headers or _idempotency_headers(),
    )

    assert response.status_code == 201
    return response.json()


async def _create_requisition(
    database_engine: AsyncEngine,
    *,
    tenant_id: UUID,
    status: RequisitionStatus,
) -> Requisition:
    """Seed a requisition for application endpoint preconditions."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=status,
            created_by_subject="recruiter-subject",
        )
        session.add(requisition)
        await session.flush()

        return requisition


@pytest.mark.asyncio
async def test_replays_candidate_creation_for_same_idempotency_key(
    api_app: FastAPI,
) -> None:
    """Replay candidate creation when the idempotency key is reused."""
    transport = ASGITransport(app=api_app)
    headers = _idempotency_headers()
    payload = {
        "full_name": "Ada Lovelace",
        "email": "ada@acme.io",
        "source": "employee_referral",
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=headers,
        )
        second = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert second.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_duplicate_candidate_with_a_new_idempotency_key(
    api_app: FastAPI,
) -> None:
    """Reject a duplicate candidate submitted with a new idempotency key."""
    transport = ASGITransport(app=api_app)
    payload = {
        "full_name": "Ada Lovelace",
        "email": "Ada.Lovelace@Acme.IO",
        "source": "employee_referral",
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=_idempotency_headers(),
        )
        second = await client.post(
            "/api/v1/candidates",
            json={
                **payload,
                    "email": "ada.lovelace@acme.io",
            },
            headers=_idempotency_headers(),
        )

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_hides_candidate_from_another_tenant(
    api_app: FastAPI,
) -> None:
    """Hide a candidate when the caller belongs to another tenant."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)

        _set_context(
            api_app,
            tenant_id=uuid4(),
            roles=frozenset({Role.RECRUITER}),
        )
        response = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate or application not found."


@pytest.mark.asyncio
async def test_candidate_get_response_is_private_and_not_cached(
    api_app: FastAPI,
) -> None:
    """Return private cache headers when retrieving a candidate."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        response = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == candidate["id"]
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_application_when_requisition_is_not_open(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject applications for requisitions that are not open."""
    transport = ASGITransport(app=api_app)
    requisition = await _create_requisition(
        database_engine,
        tenant_id=tenant_id,
        status=RequisitionStatus.DRAFT,
    )

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        response = await client.post(
            "/api/v1/applications",
            json={
                "candidate_id": candidate["id"],
                "requisition_id": str(requisition.id),
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_creates_application_for_open_requisition_and_marks_private(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create an application and return private cache headers."""
    transport = ASGITransport(app=api_app)
    requisition = await _create_requisition(
        database_engine,
        tenant_id=tenant_id,
        status=RequisitionStatus.OPEN,
    )

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        created = await client.post(
            "/api/v1/applications",
            json={
                "candidate_id": candidate["id"],
                "requisition_id": str(requisition.id),
            },
            headers=_idempotency_headers(),
        )
        fetched = await client.get(f"/api/v1/applications/{created.json()['id']}")

    assert created.status_code == 201
    assert created.json()["status"] == "applied"
    assert created.headers["Cache-Control"] == "private, no-store"
    assert fetched.status_code == 200
    assert fetched.headers["Cache-Control"] == "private, no-store"
