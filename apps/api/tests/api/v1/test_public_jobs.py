"""HTTP integration tests for anonymous public job discovery."""

import json
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from app.api.dependencies import get_db_session
from app.api.v1 import public_job_pages as public_job_pages_module
from app.core.config import Settings
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without local environment configuration."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
        public_site_base_url=AnyHttpUrl("https://jobs.example.test"),
        public_job_country_code="KE",
        jwt_issuer=AnyHttpUrl("https://issuer.example.test/"),
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url=AnyHttpUrl(
            "https://issuer.example.test/.well-known/jwks.json"
        ),
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    """Yield one request-scoped session for the isolated API test database."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async def override() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            finally:
                await session.rollback()

    return override


async def _seed_public_job(
    engine: AsyncEngine,
    *,
    position: int,
    status: JobPostingStatus = JobPostingStatus.PUBLISHED,
    requisition_status: RequisitionStatus = RequisitionStatus.OPEN,
    published_at: datetime | None = None,
    expires_at: datetime | None = None,
    title: str | None = None,
    department: str = "Engineering",
    location: str | None = "Nairobi, Kenya",
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
) -> JobPosting:
    """Persist a job posting with explicit public-visibility conditions."""
    tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        tenant = Tenant(
            id=tenant_id,
            name=f"Public Jobs Tenant {position}",
            slug=f"public-jobs-{position}-{tenant_id.hex[:8]}",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title=title or f"Backend Engineer {position}",
            description=f"Public job description {position}.",
            department=department,
            location=location,
            headcount=1,
            status=requisition_status,
            created_by_subject="seed",
        )
        session.add_all([tenant, requisition])
        await session.flush()

        posting = JobPosting(
            tenant_id=tenant_id,
            requisition_id=requisition.id,
            public_id=uuid4(),
            slug=f"backend-engineer-{position}-{tenant_id.hex[:8]}",
            title=title or f"Backend Engineer {position}",
            description=f"Public job description {position}.",
            department=department,
            location=location,
            employment_type=employment_type,
            status=status,
            published_at=published_at,
            expires_at=expires_at,
            created_by_subject="seed",
        )
        session.add(posting)
        await session.flush()
        return posting


@pytest.fixture(name="public_jobs_app")
async def _public_jobs_app_fixture(
    database_engine: AsyncEngine,
) -> AsyncGenerator[FastAPI, None]:
    """Create an API app requiring no caller identity for public endpoints."""
    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )

    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )

    yield application

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_lists_only_currently_visible_jobs_with_safe_fields_and_cache_headers(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Expose only published, non-expired jobs for open requisitions."""
    now = datetime.now(UTC)
    visible = await _seed_public_job(
        database_engine,
        position=1,
        published_at=now,
        expires_at=now + timedelta(days=7),
    )
    await _seed_public_job(
        database_engine,
        position=2,
        status=JobPostingStatus.DRAFT,
        published_at=None,
    )
    await _seed_public_job(
        database_engine,
        position=3,
        status=JobPostingStatus.UNPUBLISHED,
        published_at=now,
    )
    await _seed_public_job(
        database_engine,
        position=4,
        status=JobPostingStatus.EXPIRED,
        published_at=now,
        expires_at=now - timedelta(days=1),
    )
    await _seed_public_job(
        database_engine,
        position=5,
        published_at=now,
        requisition_status=RequisitionStatus.CLOSED,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/public/jobs")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == (
        "public, max-age=60, stale-while-revalidate=300"
    )

    payload = response.json()
    assert [item["public_id"] for item in payload["items"]] == [
        str(visible.public_id)
    ]

    serialized = str(payload)
    for private_field in (
        "tenant_id",
        "requisition_id",
        "created_by_subject",
        "version",
        "status",
        "internal",
    ):
        assert private_field not in serialized


@pytest.mark.asyncio
async def test_returns_public_job_detail_and_hides_non_public_records(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Public detail does not reveal drafts, expired jobs, or closed requisitions."""
    now = datetime.now(UTC)
    visible = await _seed_public_job(
        database_engine,
        position=10,
        published_at=now,
        title="Principal Platform Engineer",
    )
    hidden = await _seed_public_job(
        database_engine,
        position=11,
        status=JobPostingStatus.UNPUBLISHED,
        published_at=now,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        detail = await client.get(
            f"/api/v1/public/jobs/{visible.public_id}"
        )
        hidden_detail = await client.get(
            f"/api/v1/public/jobs/{hidden.public_id}"
        )
        nonexistent = await client.get(f"/api/v1/public/jobs/{uuid4()}")

    assert detail.status_code == 200
    assert detail.headers["Cache-Control"] == (
        "public, max-age=60, stale-while-revalidate=300"
    )
    assert detail.json()["title"] == "Principal Platform Engineer"
    assert detail.json()["description"] == "Public job description 10."
    assert "tenant_id" not in detail.json()
    assert "requisition_id" not in detail.json()

    assert hidden_detail.status_code == 404
    assert hidden_detail.json()["detail"] == "Job posting not found."
    assert nonexistent.status_code == 404
    assert nonexistent.json()["detail"] == "Job posting not found."


@pytest.mark.asyncio
async def test_html_job_page_has_canonical_url_and_google_job_posting_json_ld(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Render candidate-visible HTML and safe, crawlable structured data."""
    now = datetime.now(UTC)
    posting = await _seed_public_job(
        database_engine,
        position=80,
        published_at=now,
        expires_at=now + timedelta(days=30),
        title='Engineer </script><script>alert("x")</script>',
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/jobs/{posting.public_id}/{posting.slug}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["Cache-Control"] == ("public, max-age=60, stale-while-revalidate=300")
    assert (
        f'<link rel="canonical" href="https://jobs.example.test/jobs/'
        f'{posting.public_id}/{posting.slug}">'
    ) in response.text
    assert "\\u003c/script\\u003e" in response.text
    assert '<script>alert("x")</script>' not in response.text

    json_ld = response.text.split('<script type="application/ld+json">', maxsplit=1)[1].split(
        "</script>", maxsplit=1
    )[0]
    structured_data = json.loads(json_ld)
    assert structured_data["@context"] == "https://schema.org"
    assert structured_data["@type"] == "JobPosting"
    assert structured_data["hiringOrganization"]["name"] == "Public Jobs Tenant 80"
    assert structured_data["jobLocation"]["address"]["addressCountry"] == "KE"
    assert structured_data["employmentType"] == "FULL_TIME"
    assert structured_data["validThrough"].endswith("Z")
    assert structured_data["url"] == (
        f"https://jobs.example.test/jobs/{posting.public_id}/{posting.slug}"
    )
    for private_field in ("tenant_id", "requisition_id", "created_by_subject"):
        assert private_field not in structured_data


@pytest.mark.asyncio
async def test_html_job_page_redirects_old_slugs_and_hides_non_public_postings(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Canonicalize stale slugs and keep non-public postings inaccessible."""
    visible = await _seed_public_job(
        database_engine,
        position=81,
        published_at=datetime.now(UTC),
    )
    hidden = await _seed_public_job(
        database_engine,
        position=82,
        status=JobPostingStatus.UNPUBLISHED,
        published_at=datetime.now(UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
        follow_redirects=False,
    ) as client:
        old_slug = await client.get(f"/jobs/{visible.public_id}/old-slug")
        hidden_page = await client.get(f"/jobs/{hidden.public_id}/{hidden.slug}")

    assert old_slug.status_code == 301
    assert old_slug.headers["location"].endswith(f"/jobs/{visible.public_id}/{visible.slug}")
    assert hidden_page.status_code == 404


@pytest.mark.asyncio
async def test_sitemap_contains_only_currently_visible_public_job_pages(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Publish canonical URLs but omit drafts, expired jobs, and closed jobs."""
    now = datetime.now(UTC)
    visible = await _seed_public_job(
        database_engine,
        position=83,
        published_at=now,
    )
    draft = await _seed_public_job(
        database_engine,
        position=84,
        status=JobPostingStatus.DRAFT,
    )
    expired = await _seed_public_job(
        database_engine,
        position=85,
        published_at=now,
        expires_at=now - timedelta(minutes=1),
    )
    closed = await _seed_public_job(
        database_engine,
        position=86,
        published_at=now,
        requisition_status=RequisitionStatus.CLOSED,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert response.headers["Cache-Control"] == ("public, max-age=300, stale-while-revalidate=600")
    assert b"urlset" in response.content
    assert f"https://jobs.example.test/jobs/{visible.public_id}/{visible.slug}" in response.text
    for hidden_posting in (draft, expired, closed):
        assert str(hidden_posting.public_id) not in response.text


@pytest.mark.asyncio
async def test_public_job_without_required_structured_data_fields_is_still_safe_html(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Do not invent a location or emit ineligible JobPosting markup."""
    posting = await _seed_public_job(
        database_engine,
        position=87,
        published_at=datetime.now(UTC),
        location=None,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(f"/jobs/{posting.public_id}/{posting.slug}")

    assert response.status_code == 200
    assert "application/ld+json" not in response.text
    assert "Public job description 87." in response.text


@pytest.mark.asyncio
async def test_robots_txt_advertises_sitemap_and_excludes_versioned_api(
    public_jobs_app: FastAPI,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "Allow: /jobs/" in response.text
    assert "Disallow: /api/" in response.text
    assert "Sitemap: https://jobs.example.test/sitemap.xml" in response.text


@pytest.mark.asyncio
async def test_large_sitemap_uses_bounded_shards(
    public_jobs_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shard large sitemaps below protocol limits with deterministic offsets."""
    from app.services.public_jobs import PublicJobSitemapEntry

    async def count_entries(_: AsyncSession) -> int:
        return 40_001

    observed: dict[str, int] = {}

    async def list_entries(
        _: AsyncSession,
        *,
        offset: int,
        limit: int,
    ) -> list[PublicJobSitemapEntry]:
        observed["offset"] = offset
        observed["limit"] = limit
        return [
            PublicJobSitemapEntry(
                public_id=uuid4(),
                slug="example-role",
                updated_at=datetime.now(UTC),
            )
        ]

    monkeypatch.setattr(
        public_job_pages_module,
        "count_public_job_sitemap_entries",
        count_entries,
    )
    monkeypatch.setattr(
        public_job_pages_module,
        "list_public_job_sitemap_entries",
        list_entries,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        index = await client.get("/sitemap.xml")
        shard = await client.get("/sitemap/jobs/2.xml")

    assert index.status_code == 200
    assert b"sitemapindex" in index.content
    assert b"https://jobs.example.test/sitemap/jobs/2.xml" in index.content
    assert shard.status_code == 200
    assert b"urlset" in shard.content
    assert observed == {"offset": 40_000, "limit": 40_000}


@pytest.mark.asyncio
async def test_filters_and_keyset_paginates_visible_public_jobs(
    public_jobs_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Apply safe filters and return deterministic non-duplicating pages."""
    now = datetime.now(UTC)
    newest = await _seed_public_job(
        database_engine,
        position=20,
        published_at=now,
        title="Senior Python Engineer",
        department="Engineering",
        location="Nairobi, Kenya",
        employment_type=EmploymentType.FULL_TIME,
    )
    middle = await _seed_public_job(
        database_engine,
        position=21,
        published_at=now - timedelta(minutes=1),
        title="Python Platform Engineer",
        department="Engineering",
        location="Remote - Kenya",
        employment_type=EmploymentType.CONTRACT,
    )
    oldest = await _seed_public_job(
        database_engine,
        position=22,
        published_at=now - timedelta(minutes=2),
        title="Finance Analyst",
        department="Finance",
        location="Nairobi, Kenya",
        employment_type=EmploymentType.FULL_TIME,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        filtered = await client.get(
            "/api/v1/public/jobs",
            params={
                "query": "python",
                "department": "engineering",
                "location": "kenya",
            },
        )
        first_page = await client.get(
            "/api/v1/public/jobs",
            params={"limit": 2},
        )
        second_page = await client.get(
            "/api/v1/public/jobs",
            params={
                "limit": 2,
                "cursor": first_page.json()["next_cursor"],
            },
        )

    assert filtered.status_code == 200
    assert [item["public_id"] for item in filtered.json()["items"]] == [
        str(newest.public_id),
        str(middle.public_id),
    ]

    returned_ids = [
        item["public_id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ]
    assert returned_ids == [
        str(newest.public_id),
        str(middle.public_id),
        str(oldest.public_id),
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_rejects_invalid_public_cursor(
    public_jobs_app: FastAPI,
) -> None:
    """Malformed pagination state returns a safe validation response."""
    async with AsyncClient(
        transport=ASGITransport(app=public_jobs_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/public/jobs",
            params={"cursor": "not-a-valid-cursor"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid public job cursor."
