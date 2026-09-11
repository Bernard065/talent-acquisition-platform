"""HTTP integration tests for private job-posting management reads."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
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
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import EmploymentType, JobPostingStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


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
    """Return a verified caller dependency for one tenant and role set."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="job-posting-reader",
            roles=roles,
            request_id="test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide a request-scoped session against the isolated test database."""
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
    """Replace the authenticated caller for a subsequent request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


def _idempotency_headers() -> dict[str, str]:
    """Return a unique idempotency key for one write request."""
    return {"Idempotency-Key": str(uuid4())}


async def _seed_requisition(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    requisition_status: RequisitionStatus = RequisitionStatus.OPEN,
) -> Requisition:
    """Persist one requisition for job-posting endpoint preconditions."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Platform Engineer",
            description="Build reliable recruiting platform services.",
            department="Engineering",
            location="Nairobi, Kenya",
            headcount=1,
            status=requisition_status,
            created_by_subject="seed",
        )
        session.add(requisition)
        await session.flush()
        return requisition


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the primary tenant used by the API tests."""
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
                name="Job Posting API Tenant",
                slug=f"job-posting-api-{value.hex[:12]}",
            )
        )

    return value


@pytest_asyncio.fixture(name="job_postings_api_app")
async def job_postings_api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with database and verified identity dependencies overridden."""
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


async def _seed_job_posting(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    position: int,
    updated_at: datetime,
    posting_status: JobPostingStatus = JobPostingStatus.DRAFT,
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    published_at: datetime | None = None,
    requisition_status: RequisitionStatus = RequisitionStatus.OPEN,
) -> JobPosting:
    """Persist one tenant-owned posting with deterministic ordering values."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        requisition = Requisition(
            tenant_id=tenant_id,
            title=f"Requisition {position}",
            description=f"Internal requisition description {position}.",
            department="Engineering",
            location="Nairobi, Kenya",
            headcount=1,
            status=requisition_status,
            created_by_subject="seed",
        )
        session.add(requisition)
        await session.flush()

        posting = JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            public_id=uuid4(),
            slug=f"backend-engineer-{position}-{uuid4().hex[:8]}",
            title=f"Backend Engineer {position}",
            description=f"Job posting description {position}.",
            department="Engineering",
            location="Nairobi, Kenya",
            employment_type=employment_type,
            status=posting_status,
            published_at=published_at,
            created_by_subject="seed",
            created_at=updated_at,
            updated_at=updated_at,
        )
        session.add(posting)
        await session.flush()

        return posting


@pytest.mark.asyncio
async def test_lists_tenant_postings_with_filters_and_private_cache_headers(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """List only caller-tenant postings and apply supported filters."""
    now = datetime.now(UTC).replace(microsecond=0)

    matching = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=1,
        updated_at=now,
        posting_status=JobPostingStatus.PUBLISHED,
        employment_type=EmploymentType.CONTRACT,
        published_at=now - timedelta(days=1),
    )
    await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=2,
        updated_at=now - timedelta(minutes=1),
        posting_status=JobPostingStatus.DRAFT,
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/job-postings",
            params={
                "status": "published",
                "employment_type": "contract",
                "published_after": (now - timedelta(days=2)).isoformat(),
                "published_before": now.isoformat(),
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"

    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [str(matching.id)]


@pytest.mark.asyncio
async def test_cursor_pagination_is_stable_and_has_no_duplicates(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Use a stable keyset cursor across multiple result pages."""
    now = datetime.now(UTC).replace(microsecond=0)

    newest = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=10,
        updated_at=now,
    )
    middle = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=11,
        updated_at=now - timedelta(minutes=1),
    )
    oldest = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=12,
        updated_at=now - timedelta(minutes=2),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        first_page = await client.get(
            "/api/v1/job-postings",
            params={"limit": 2},
        )
        second_page = await client.get(
            "/api/v1/job-postings",
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
    assert returned_ids == [
        str(newest.id),
        str(middle.id),
        str(oldest.id),
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_hides_another_tenants_job_posting(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Return 404 rather than disclosing a job posting in another tenant."""
    other_tenant_id = uuid4()
    now = datetime.now(UTC)

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=other_tenant_id,
                name="Other Tenant",
                slug=f"other-job-posting-{other_tenant_id.hex[:12]}",
            )
        )

    other_posting = await _seed_job_posting(
        database_engine,
        tenant_id=other_tenant_id,
        position=20,
        updated_at=now,
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            f"/api/v1/job-postings/{other_posting.id}",
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job posting not found."
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_roles_without_job_posting_read_access(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Interviewers cannot use private job-posting management endpoints."""
    now = datetime.now(UTC)
    posting = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=30,
        updated_at=now,
    )
    _set_context(
        job_postings_api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/v1/job-postings/{posting.id}")

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_invalid_cursor_and_naive_date(
    job_postings_api_app: FastAPI,
) -> None:
    """Reject malformed pagination state and timezone-unsafe date bounds."""
    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        invalid_cursor = await client.get(
            "/api/v1/job-postings",
            params={"cursor": "not-a-valid-cursor"},
        )
        naive_date = await client.get(
            "/api/v1/job-postings",
            params={"published_after": "2026-09-11T10:00:00"},
        )

    assert invalid_cursor.status_code == 422
    assert invalid_cursor.headers["Cache-Control"] == "private, no-store"

    assert naive_date.status_code == 422
    assert naive_date.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_detail_response_has_only_safe_private_fields(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Do not expose tenant ownership or actor identifiers in API responses."""
    posting = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=40,
        updated_at=datetime.now(UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/api/v1/job-postings/{posting.id}")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"

    payload: dict[str, Any] = response.json()
    assert payload["id"] == str(posting.id)
    assert payload["title"] == posting.title

    for prohibited_field in ("tenant_id", "created_by_subject"):
        assert prohibited_field not in payload


@pytest.mark.asyncio
async def test_replays_job_posting_creation_for_same_idempotency_key(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create one draft posting and replay its exact persisted response."""
    requisition = await _seed_requisition(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _idempotency_headers()
    payload = {
        "employment_type": "full_time",
        "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
    }

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/requisitions/{requisition.id}/job-postings",
            json=payload,
            headers=headers,
        )
        second = await client.post(
            f"/api/v1/requisitions/{requisition.id}/job-postings",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["status"] == "draft"
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert second.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_publishes_and_unpublishes_a_job_posting(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Publish an eligible draft and explicitly remove it from public visibility."""
    posting = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=50,
        updated_at=datetime.now(UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        published = await client.post(
            f"/api/v1/job-postings/{posting.id}/publish",
            json={"expected_version": posting.version},
            headers=_idempotency_headers(),
        )
        unpublished = await client.post(
            f"/api/v1/job-postings/{posting.id}/unpublish",
            json={"expected_version": published.json()["version"]},
            headers=_idempotency_headers(),
        )

    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_at"] is not None
    assert published.headers["Cache-Control"] == "private, no-store"

    assert unpublished.status_code == 200
    assert unpublished.json()["status"] == "unpublished"
    assert unpublished.json()["unpublished_at"] is not None
    assert unpublished.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_stale_job_posting_version(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject a workflow update that does not use the current version."""
    posting = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=51,
        updated_at=datetime.now(UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/job-postings/{posting.id}/publish",
            json={"expected_version": posting.version + 1},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_publication_for_non_open_requisition(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Do not allow public visibility when the requisition is not open."""
    posting = await _seed_job_posting(
        database_engine,
        tenant_id=tenant_id,
        position=52,
        updated_at=datetime.now(UTC),
        requisition_status=RequisitionStatus.ON_HOLD,
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/job-postings/{posting.id}/publish",
            json={"expected_version": posting.version},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_job_posting_workflow_for_unauthorized_role(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Interviewers cannot create or publish job postings."""
    requisition = await _seed_requisition(
        database_engine,
        tenant_id=tenant_id,
    )
    _set_context(
        job_postings_api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/requisitions/{requisition.id}/job-postings",
            json={"employment_type": "full_time"},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_hides_job_posting_workflow_outside_callers_tenant(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Do not disclose another tenant's workflow resource."""
    other_tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=other_tenant_id,
                name="Other Job Posting Tenant",
                slug=f"other-job-posting-{other_tenant_id.hex[:12]}",
            )
        )

    other_posting = await _seed_job_posting(
        database_engine,
        tenant_id=other_tenant_id,
        position=53,
        updated_at=datetime.now(UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/job-postings/{other_posting.id}/publish",
            json={"expected_version": other_posting.version},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job posting not found."
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_unknown_job_posting_workflow_fields(
    job_postings_api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject unknown JSON input instead of silently accepting it."""
    requisition = await _seed_requisition(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=job_postings_api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/requisitions/{requisition.id}/job-postings",
            json={
                "employment_type": "full_time",
                "unexpected_internal_field": "not accepted",
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 422
