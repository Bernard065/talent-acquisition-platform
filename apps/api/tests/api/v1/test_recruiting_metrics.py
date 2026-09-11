"""HTTP integration tests for private recruiting analytics."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.application import Application
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app

_WINDOW_START = datetime(2026, 9, 1, tzinfo=UTC)
_WINDOW_END = datetime(2026, 9, 11, tzinfo=UTC)


def _test_settings() -> Settings:
    """Build isolated settings without relying on local environment files."""
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
    """Return one verified test caller."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="analytics-api-user",
            roles=roles,
            request_id="analytics-api-test-request",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped database session override."""
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
    """Replace the verified caller for a subsequent request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


async def _seed_tenant(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> None:
    """Create one tenant required by metrics foreign keys."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Analytics API Tenant {tenant_id.hex[:12]}",
                slug=f"analytics-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_hired_application(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    position: int,
    source: str,
    email: str,
) -> None:
    """Create a hired application with typed, private lifecycle history."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name=f"Candidate {position}",
            email=email,
            normalized_email=email.lower(),
            source=source,
            source_metadata={"campaign": "private-campaign"},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title=f"Platform Engineer {position}",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="seed",
        )
        session.add_all([candidate, requisition])
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.HIRED,
            applied_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
            created_by_subject="seed",
        )
        session.add(application)
        await session.flush()

        session.add_all(
            [
                ApplicationStageHistory(
                    tenant_id=tenant_id,
                    application_id=application.id,
                    from_status=None,
                    to_status=ApplicationStatus.APPLIED,
                    transitioned_by_subject="seed",
                    transitioned_at=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
                ),
                ApplicationStageHistory(
                    tenant_id=tenant_id,
                    application_id=application.id,
                    from_status=ApplicationStatus.APPLIED,
                    to_status=ApplicationStatus.HIRED,
                    transitioned_by_subject="seed",
                    transitioned_at=datetime(2026, 9, 5, 9, 0, tzinfo=UTC),
                ),
            ]
        )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the primary tenant used by API tests."""
    value = uuid4()
    await _seed_tenant(database_engine, tenant_id=value)
    return value


@pytest_asyncio.fixture(name="analytics_api_app")
async def analytics_api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with database and verified identity overrides."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    _set_context(
        application,
        tenant_id=tenant_id,
        roles=frozenset({Role.ANALYST}),
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


def _metrics_params(
    *,
    starts_at: datetime = _WINDOW_START,
    ends_at: datetime = _WINDOW_END,
) -> dict[str, str]:
    """Build valid query parameters for the aggregate metrics endpoint."""
    return {
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_returns_private_aggregate_metrics_without_candidate_data(
    analytics_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Return aggregate data only and explicitly prevent shared caching."""
    await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
        position=1,
        source="employee_referral",
        email="private.candidate@example.test",
    )

    async with AsyncClient(
        transport=ASGITransport(app=analytics_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/analytics/recruiting-metrics",
            params=_metrics_params(),
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"

    payload = response.json()
    assert payload["starts_at"] == _WINDOW_START.isoformat()
    assert payload["ends_at"] == _WINDOW_END.isoformat()

    funnel = {item["status"]: item["count"] for item in payload["funnel"]}
    assert funnel["applied"] == 1
    assert funnel["hired"] == 1

    assert payload["source_effectiveness"] == [
        {
            "source": "employee_referral",
            "application_count": 1,
            "hired_count": 1,
        }
    ]
    assert payload["time_to_hire"] == {
        "hired_count": 1,
        "average_hours": 96.0,
    }

    assert set(payload) == {
        "starts_at",
        "ends_at",
        "funnel",
        "stage_transitions",
        "source_effectiveness",
        "time_to_hire",
    }

    serialized = str(payload)
    for prohibited_value in (
        "private.candidate@example.test",
        "Candidate 1",
        "private-campaign",
        "candidate_id",
        "email",
        "phone",
        "tenant_id",
    ):
        assert prohibited_value not in serialized


@pytest.mark.asyncio
async def test_enforces_role_authorization(
    analytics_api_app: FastAPI,
    tenant_id: UUID,
) -> None:
    """Reject roles that cannot view tenant-wide recruiting metrics."""
    _set_context(
        analytics_api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=analytics_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/analytics/recruiting-metrics",
            params=_metrics_params(),
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_enforces_tenant_isolation(
    analytics_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Do not aggregate applications belonging to another tenant."""
    other_tenant_id = uuid4()
    await _seed_tenant(database_engine, tenant_id=other_tenant_id)

    await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
        position=2,
        source="employee_referral",
        email="tenant-a@example.test",
    )
    await _seed_hired_application(
        database_engine,
        tenant_id=other_tenant_id,
        position=3,
        source="job_board",
        email="tenant-b@example.test",
    )

    async with AsyncClient(
        transport=ASGITransport(app=analytics_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/analytics/recruiting-metrics",
            params=_metrics_params(),
        )

    assert response.status_code == 200

    payload = response.json()
    funnel = {item["status"]: item["count"] for item in payload["funnel"]}

    assert funnel["applied"] == 1
    assert funnel["hired"] == 1
    assert payload["source_effectiveness"] == [
        {
            "source": "employee_referral",
            "application_count": 1,
            "hired_count": 1,
        }
    ]


@pytest.mark.asyncio
async def test_rejects_timezone_unsafe_and_unbounded_windows(
    analytics_api_app: FastAPI,
) -> None:
    """Reject naive timestamps and excessive reporting date ranges."""
    async with AsyncClient(
        transport=ASGITransport(app=analytics_api_app),
        base_url="http://testserver",
    ) as client:
        naive_response = await client.get(
            "/api/v1/analytics/recruiting-metrics",
            params={
                "starts_at": "2026-09-01T00:00:00",
                "ends_at": "2026-09-02T00:00:00+00:00",
            },
        )
        long_window_response = await client.get(
            "/api/v1/analytics/recruiting-metrics",
            params=_metrics_params(
                starts_at=_WINDOW_START,
                ends_at=datetime(2027, 9, 3, tzinfo=UTC),
            ),
        )

    assert naive_response.status_code == 422
    assert naive_response.headers["Cache-Control"] == "private, no-store"

    assert long_window_response.status_code == 422
    assert (
        long_window_response.headers["Cache-Control"]
        == "private, no-store"
    )
