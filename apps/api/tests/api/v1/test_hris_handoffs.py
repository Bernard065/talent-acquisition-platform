"""HTTP integration tests for private HRIS handoff operations."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.domains.hris.enums import HrisHandoffStatus
from app.main import create_app
from tests.services.test_hris_handoff_operations import _seed_handoffs


def _settings() -> Settings:
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
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return a verified caller context for one test request."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="hris-handoff-api-admin",
            roles=roles,
            request_id="hris-handoff-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide isolated request-scoped asynchronous database sessions."""
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
    """Switch the simulated verified caller identity."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles=roles,
    )


async def _seed_operations(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    entries: tuple[tuple[HrisHandoffStatus, datetime], ...],
):
    """Seed private HRIS handoff records through the shared PostgreSQL helper."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        return await _seed_handoffs(
            session,
            tenant_id=tenant_id,
            entries=entries,
        )


@pytest_asyncio.fixture(name="hris_handoffs_app")
async def hris_handoffs_app_fixture(
    database_engine: AsyncEngine,
) -> AsyncIterator[FastAPI]:
    """Create the API with database and verified-identity overrides."""
    application = create_app(_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )

    _set_context(
        application,
        tenant_id=uuid4(),
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    yield application

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_requires_tenant_admin_for_hris_handoff_operations(
    hris_handoffs_app: FastAPI,
) -> None:
    """Recruiters cannot inspect private operational handoff state."""
    _set_context(
        hris_handoffs_app,
        tenant_id=uuid4(),
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=hris_handoffs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/hris/handoffs")

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_lists_only_safe_handoffs_owned_by_callers_tenant(
    hris_handoffs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Tenant isolation and response shaping prevent operational data leakage."""
    owner_tenant_id = uuid4()
    other_tenant_id = uuid4()
    now = datetime.now(UTC)

    owned_handoff = (
        await _seed_operations(
            database_engine,
            tenant_id=owner_tenant_id,
            entries=((HrisHandoffStatus.PENDING, now),),
        )
    )[0]
    other_handoff = (
        await _seed_operations(
            database_engine,
            tenant_id=other_tenant_id,
            entries=((HrisHandoffStatus.FAILED, now + timedelta(minutes=1)),),
        )
    )[0]

    _set_context(
        hris_handoffs_app,
        tenant_id=owner_tenant_id,
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=hris_handoffs_app),
        base_url="http://testserver",
    ) as client:
        listed = await client.get("/api/v1/hris/handoffs")
        owned = await client.get(
            f"/api/v1/hris/handoffs/{owned_handoff.id}"
        )
        hidden = await client.get(
            f"/api/v1/hris/handoffs/{other_handoff.id}"
        )

    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "private, no-store"
    assert [item["id"] for item in listed.json()["items"]] == [
        str(owned_handoff.id)
    ]

    assert owned.status_code == 200
    assert owned.headers["Cache-Control"] == "private, no-store"

    item = owned.json()
    assert set(item) == {
        "id",
        "provider",
        "status",
        "version",
        "attempt_count",
        "last_error_code",
        "last_attempt_at",
        "succeeded_at",
        "external_employee_reference",
        "created_at",
        "updated_at",
    }

    serialized = str(item).lower()
    for prohibited_field in (
        "tenant_id",
        "application_id",
        "onboarding_instance_id",
        "hris_connection_id",
        "credential_reference",
        "external_idempotency_key",
        "template_snapshot",
        "payload",
    ):
        assert prohibited_field not in serialized

    assert hidden.status_code == 404
    assert hidden.headers["Cache-Control"] == "private, no-store"
    assert hidden.json()["detail"] == "HRIS handoff not found."


@pytest.mark.asyncio
async def test_filters_hris_handoffs_by_status_and_created_range(
    hris_handoffs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Status and date filters are applied only within the authenticated tenant."""
    tenant_id = uuid4()
    base_time = datetime(2026, 1, 1, tzinfo=UTC)

    handoffs = await _seed_operations(
        database_engine,
        tenant_id=tenant_id,
        entries=(
            (HrisHandoffStatus.PENDING, base_time),
            (HrisHandoffStatus.RETRYABLE_FAILED, base_time + timedelta(days=1)),
            (HrisHandoffStatus.FAILED, base_time + timedelta(days=2)),
        ),
    )

    _set_context(
        hris_handoffs_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=hris_handoffs_app),
        base_url="http://testserver",
    ) as client:
        failed = await client.get(
            "/api/v1/hris/handoffs",
            params={"status": "failed"},
        )
        ranged = await client.get(
            "/api/v1/hris/handoffs",
            params={
                "created_from": (base_time + timedelta(hours=12)).isoformat(),
                "created_to": (
                    base_time + timedelta(days=1, hours=12)
                ).isoformat(),
            },
        )

    assert failed.status_code == 200
    assert [item["id"] for item in failed.json()["items"]] == [
        str(handoffs[2].id)
    ]

    assert ranged.status_code == 200
    assert [item["id"] for item in ranged.json()["items"]] == [
        str(handoffs[1].id)
    ]


@pytest.mark.asyncio
async def test_paginates_hris_handoffs_without_duplicates(
    hris_handoffs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Keyset cursors remain stable even when handoffs share timestamps."""
    tenant_id = uuid4()
    shared_timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    handoffs = await _seed_operations(
        database_engine,
        tenant_id=tenant_id,
        entries=(
            (HrisHandoffStatus.PENDING, shared_timestamp),
            (HrisHandoffStatus.PENDING, shared_timestamp),
            (HrisHandoffStatus.PENDING, shared_timestamp),
        ),
    )

    _set_context(
        hris_handoffs_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=hris_handoffs_app),
        base_url="http://testserver",
    ) as client:
        first_page = await client.get(
            "/api/v1/hris/handoffs",
            params={"limit": 2},
        )
        second_page = await client.get(
            "/api/v1/hris/handoffs",
            params={
                "limit": 2,
                "cursor": first_page.json()["next_cursor"],
            },
        )

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    returned_ids = [
        item["id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ]
    expected_ids = [
        str(handoff.id)
        for handoff in sorted(handoffs, key=lambda handoff: handoff.id, reverse=True)
    ]

    assert returned_ids == expected_ids
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_rejects_malformed_cursors_and_invalid_filters(
    hris_handoffs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Reject invalid operational queries without leaking implementation details."""
    tenant_id = uuid4()
    await _seed_operations(
        database_engine,
        tenant_id=tenant_id,
        entries=((HrisHandoffStatus.PENDING, datetime.now(UTC)),),
    )

    _set_context(
        hris_handoffs_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=hris_handoffs_app),
        base_url="http://testserver",
    ) as client:
        invalid_cursor = await client.get(
            "/api/v1/hris/handoffs",
            params={"cursor": "not-a-valid-cursor"},
        )
        invalid_status = await client.get(
            "/api/v1/hris/handoffs",
            params={"status": "not-a-status"},
        )
        invalid_date = await client.get(
            "/api/v1/hris/handoffs",
            params={"created_from": "not-a-date"},
        )
        invalid_limit = await client.get(
            "/api/v1/hris/handoffs",
            params={"limit": 101},
        )

    for response in (
        invalid_cursor,
        invalid_status,
        invalid_date,
        invalid_limit,
    ):
        assert response.status_code == 422
        assert response.headers["Cache-Control"] == "private, no-store"

    assert invalid_cursor.json()["detail"] == "Invalid HRIS handoff cursor."
    assert "not-a-valid-cursor" not in invalid_cursor.text
