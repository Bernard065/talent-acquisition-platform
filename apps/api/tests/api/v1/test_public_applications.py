"""HTTP integration tests for anonymous public application submission."""

from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.sql.functions import count as sql_count

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant
from app.db.models.job_posting import JobPosting
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.job_postings.enums import (
    EmploymentType,
    JobPostingStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app
from app.services.abuse_control import (
    AbuseControlRejectedError,
    AbuseControlUnavailableError,
    PublicApplicationAbuseCheck,
)


class AllowAbuseGuard:
    """Test abuse-control adapter that accepts every request."""

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Allow the request without retaining request metadata."""
        del check


class RejectAbuseGuard:
    """Test abuse-control adapter that rejects every request."""

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Reject the request without exposing provider-specific details."""
        del check
        raise AbuseControlRejectedError("rejected")


class UnavailableAbuseGuard:
    """Test adapter that simulates a temporary provider outage."""

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Raise a classified retryable provider failure."""
        del check
        raise AbuseControlUnavailableError("unavailable")


def _test_settings() -> Settings:
    """Build isolated API settings without local environment values."""
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


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncGenerator[AsyncSession, None]]:
    """Return a request-scoped session dependency for the test database."""
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


def _headers() -> dict[str, str]:
    """Return an idempotency key required by public submission."""
    return {"Idempotency-Key": str(uuid4())}


def _payload(**overrides: object) -> dict[str, object]:
    """Build a valid public application request."""
    return {
        "full_name": "Ada Lovelace",
        "email": "ada.lovelace@acme.co.ke",
        "phone": "+254700000000",
        "location": "Nairobi, Kenya",
        "source_reference": "careers-page",
        "privacy_consent": True,
        **overrides,
    }


async def _seed_job(
    engine: AsyncEngine,
    *,
    posting_status: JobPostingStatus = JobPostingStatus.PUBLISHED,
    requisition_status: RequisitionStatus = RequisitionStatus.OPEN,
    expires_at: datetime | None = None,
) -> JobPosting:
    """Create a public-job fixture with controllable visibility."""
    tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Public Application Tenant {tenant_id.hex[:12]}",
                slug=f"public-application-{tenant_id.hex[:12]}",
            )
        )
        await session.flush()

        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            description="Public job description.",
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
            slug=f"senior-backend-engineer-{tenant_id.hex[:12]}",
            title=requisition.title,
            description=requisition.description,
            department=requisition.department,
            location=requisition.location,
            employment_type=EmploymentType.FULL_TIME,
            status=posting_status,
            published_at=(
                datetime.now(UTC)
                if posting_status is JobPostingStatus.PUBLISHED
                else None
            ),
            expires_at=expires_at,
            created_by_subject="seed",
        )
        session.add(posting)
        await session.flush()

        return posting


async def _submission_counts(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> tuple[int, int]:
    """Count stored candidates and applications without exposing them publicly."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        candidate_count = await session.scalar(
            select(sql_count(Candidate.id)).where(
                Candidate.tenant_id == tenant_id
            )
        )
        application_count = await session.scalar(
            select(sql_count(Application.id)).where(
                Application.tenant_id == tenant_id
            )
        )

    return int(candidate_count or 0), int(application_count or 0)


@pytest_asyncio.fixture(name="public_applications_app")
async def public_applications_app_fixture(
    database_engine: AsyncEngine,
) -> AsyncGenerator[FastAPI, None]:
    """Create an anonymous API app with a deterministic abuse-control adapter."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.state.public_application_abuse_guard = AllowAbuseGuard()

    yield application

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accepts_new_public_application_without_exposing_identity(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Create internal records while returning only a generic acknowledgement."""
    posting = await _seed_job(database_engine)

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert response.status_code == 202
    assert response.json() == {"message": "Application received."}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Idempotent-Replayed"] == "false"
    assert "candidate_id" not in response.text
    assert "application_id" not in response.text
    assert candidate_count == 1
    assert application_count == 1


@pytest.mark.asyncio
async def test_replays_idempotency_key_and_hides_duplicate_submission(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Replay safely and give a new duplicate submission the same public result."""
    posting = await _seed_job(database_engine)
    headers = _headers()

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=headers,
        )
        duplicate = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(full_name="Different Submitted Name"),
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert duplicate.status_code == 202
    assert first.json() == replay.json() == duplicate.json()
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert duplicate.headers["Idempotent-Replayed"] == "false"
    assert candidate_count == 1
    assert application_count == 1


@pytest.mark.asyncio
async def test_requires_explicit_consent_and_strict_fields(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Reject missing consent and unknown JSON fields before persistence."""
    posting = await _seed_job(database_engine)

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        missing_consent = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(privacy_consent=False),
            headers=_headers(),
        )
        unknown_field = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(unexpected_field="must fail"),
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert missing_consent.status_code == 422
    assert unknown_field.status_code == 422
    assert candidate_count == 0
    assert application_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("posting_status", "requisition_status", "expires_at"),
    [
        (
            JobPostingStatus.UNPUBLISHED,
            RequisitionStatus.OPEN,
            None,
        ),
        (
            JobPostingStatus.PUBLISHED,
            RequisitionStatus.CLOSED,
            None,
        ),
        (
            JobPostingStatus.PUBLISHED,
            RequisitionStatus.OPEN,
            datetime.now(UTC) - timedelta(minutes=1),
        ),
    ],
)
async def test_hides_jobs_that_cannot_accept_public_applications(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
    posting_status: JobPostingStatus,
    requisition_status: RequisitionStatus,
    expires_at: datetime | None,
) -> None:
    """Hidden, closed, expired, and nonexistent jobs are indistinguishable."""
    posting = await _seed_job(
        database_engine,
        posting_status=posting_status,
        requisition_status=requisition_status,
        expires_at=expires_at,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Job posting not found."
    assert response.headers["Cache-Control"] == "no-store"
    assert candidate_count == 0
    assert application_count == 0


@pytest.mark.asyncio
async def test_handles_abuse_rejection_and_provider_outage_safely(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Map abuse outcomes without exposing provider implementation details."""
    posting = await _seed_job(database_engine)

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        public_applications_app.state.public_application_abuse_guard = (
            RejectAbuseGuard()
        )
        rejected = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )

        public_applications_app.state.public_application_abuse_guard = (
            UnavailableAbuseGuard()
        )
        unavailable = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )

    assert rejected.status_code == 403
    assert rejected.headers["Cache-Control"] == "no-store"
    assert unavailable.status_code == 503
    assert unavailable.headers["Cache-Control"] == "no-store"
    assert unavailable.headers["Retry-After"] == "5"


@pytest.mark.asyncio
async def test_rejects_oversized_public_application_body(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Cap anonymous request bodies before application data is processed."""
    posting = await _seed_job(database_engine)
    payload = _payload(source_reference="x" * (16 * 1024))

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=payload,
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert response.status_code == 413
    assert candidate_count == 0
    assert application_count == 0


@pytest.mark.asyncio
async def test_withdrawn_candidate_receives_generic_ack_without_new_application(
    public_applications_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Do not restart candidate processing after a recorded consent withdrawal."""
    posting = await _seed_job(database_engine)
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=public_applications_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )
        async with session_factory.begin() as session:
            candidate = await session.scalar(
                select(Candidate).where(
                    Candidate.tenant_id == posting.tenant_id,
                    Candidate.normalized_email == "ada.lovelace@acme.co.ke",
                )
            )
            assert candidate is not None
            candidate.consent_status = CandidateConsentStatus.WITHDRAWN

        second = await client.post(
            f"/api/v1/public/jobs/{posting.public_id}/applications",
            json=_payload(),
            headers=_headers(),
        )

    candidate_count, application_count = await _submission_counts(
        database_engine,
        tenant_id=posting.tenant_id,
    )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json() == {"message": "Application received."}
    assert candidate_count == application_count == 1
