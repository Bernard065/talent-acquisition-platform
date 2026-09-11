"""HTTP integration tests for private recruiter search endpoints."""

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
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without loading local environment values."""
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
    """Build a verified caller dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=roles,
            request_id="recruiting-search-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build request-scoped sessions for the isolated database."""
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
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> None:
    """Set the verified caller for a following API request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles=roles,
    )


async def _seed_records(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    prefix: str,
) -> tuple[list[Candidate], list[Application]]:
    """Create tenant-local candidates and applications with stable ordering."""
    now = datetime.now(UTC)
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Search API Tenant {prefix}",
                slug=f"search-api-{prefix}-{tenant_id.hex[:8]}",
            )
        )
        await session.flush()

        requisition = Requisition(
            tenant_id=tenant_id,
            title="Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="seed",
        )
        session.add(requisition)
        await session.flush()

        candidates = [
            Candidate(
                tenant_id=tenant_id,
                full_name=f"Ada Lovelace {prefix}",
                email=f"ada-{prefix}-{tenant_id.hex[:8]}@acme.co.ke",
                normalized_email=f"ada-{prefix}-{tenant_id.hex[:8]}@acme.co.ke",
                location="Nairobi, Kenya",
                source="public_job",
                source_metadata={},
                consent_status=CandidateConsentStatus.GRANTED,
                created_by_subject="seed",
                created_at=now,
            ),
            Candidate(
                tenant_id=tenant_id,
                full_name=f"Grace Hopper {prefix}",
                email=f"grace-{prefix}-{tenant_id.hex[:8]}@acme.co.ke",
                normalized_email=(
                    f"grace-{prefix}-{tenant_id.hex[:8]}@acme.co.ke"
                ),
                location="Remote - Kenya",
                source="employee_referral",
                source_metadata={},
                consent_status=CandidateConsentStatus.UNKNOWN,
                created_by_subject="seed",
                created_at=now - timedelta(minutes=1),
            ),
            Candidate(
                tenant_id=tenant_id,
                full_name=f"Linus Torvalds {prefix}",
                email=f"linus-{prefix}-{tenant_id.hex[:8]}@acme.co.ke",
                normalized_email=(
                    f"linus-{prefix}-{tenant_id.hex[:8]}@acme.co.ke"
                ),
                location="Nairobi, Kenya",
                source="public_job",
                source_metadata={},
                consent_status=CandidateConsentStatus.GRANTED,
                created_by_subject="seed",
                created_at=now - timedelta(minutes=2),
            ),
        ]
        session.add_all(candidates)
        await session.flush()

        applications = [
            Application(
                tenant_id=tenant_id,
                candidate_id=candidates[0].id,
                requisition_id=requisition.id,
                status=ApplicationStatus.APPLIED,
                applied_at=now,
                created_by_subject="seed",
            ),
            Application(
                tenant_id=tenant_id,
                candidate_id=candidates[1].id,
                requisition_id=requisition.id,
                status=ApplicationStatus.INTERVIEW,
                applied_at=now - timedelta(minutes=1),
                created_by_subject="seed",
            ),
            Application(
                tenant_id=tenant_id,
                candidate_id=candidates[2].id,
                requisition_id=requisition.id,
                status=ApplicationStatus.REJECTED,
                applied_at=now - timedelta(minutes=2),
                created_by_subject="seed",
            ),
        ]
        session.add_all(applications)
        await session.flush()

        return candidates, applications


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture() -> UUID:
    """Return the default tenant identifier for the API caller."""
    return uuid4()


@pytest_asyncio.fixture(name="search_app")
async def search_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with test database and verified identity overrides."""
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
async def test_filters_candidates_and_returns_private_no_store_response(
    search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Filter tenant candidates while preserving private response semantics."""
    candidates, _ = await _seed_records(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=search_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/candidates",
            params={
                "query": "Ada",
                "source": "public_job",
                "location": "nairobi",
                "consent_status": "granted",
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [item["id"] for item in response.json()["items"]] == [
        str(candidates[0].id)
    ]
    assert response.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_candidate_search_uses_stable_cursor_pagination(
    search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Return every candidate once across stable keyset pages."""
    candidates, _ = await _seed_records(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=search_app),
        base_url="http://testserver",
    ) as client:
        first_page = await client.get(
            "/api/v1/candidates",
            params={"limit": 2},
        )
        second_page = await client.get(
            "/api/v1/candidates",
            params={
                "limit": 2,
                "cursor": first_page.json()["next_cursor"],
            },
        )

    returned_ids = [
        item["id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ]

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert returned_ids == [
        str(candidates[0].id),
        str(candidates[1].id),
        str(candidates[2].id),
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_filters_applications_by_status_and_candidate(
    search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Search applications using tenant-scoped pipeline filters."""
    candidates, applications = await _seed_records(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=search_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/applications",
            params={
                "status": "interview",
                "candidate_id": str(candidates[1].id),
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [item["id"] for item in response.json()["items"]] == [
        str(applications[1].id)
    ]


@pytest.mark.asyncio
async def test_enforces_role_authorization_and_tenant_isolation(
    search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Never expose another tenant's candidate or application records."""
    await _seed_records(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    other_tenant_id = uuid4()
    other_candidates, other_applications = await _seed_records(
        database_engine,
        tenant_id=other_tenant_id,
        prefix="other",
    )

    async with AsyncClient(
        transport=ASGITransport(app=search_app),
        base_url="http://testserver",
    ) as client:
        _set_context(
            search_app,
            tenant_id=tenant_id,
            roles=frozenset({Role.INTERVIEWER}),
        )
        forbidden = await client.get("/api/v1/candidates")

        _set_context(search_app, tenant_id=tenant_id)
        hidden_candidates = await client.get(
            "/api/v1/candidates",
            params={"query": "other"},
        )
        hidden_applications = await client.get(
            "/api/v1/applications",
            params={"candidate_id": str(other_candidates[0].id)},
        )

    assert forbidden.status_code == 403
    assert hidden_candidates.status_code == 200
    assert hidden_candidates.json()["items"] == []
    assert hidden_applications.status_code == 200
    assert hidden_applications.json()["items"] == []
    assert str(other_applications[0].id) not in hidden_applications.text


@pytest.mark.asyncio
async def test_rejects_malformed_cursor(
    search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Map malformed cursor state to a safe validation response."""
    await _seed_records(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=search_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/candidates",
            params={"cursor": "not-a-valid-cursor"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid recruiter search cursor."
