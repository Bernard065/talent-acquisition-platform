"""HTTP integration tests for interview session lifecycle endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql.ranges import Range
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.application import Application
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewParticipant, InterviewSession
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.interviews.enums import (
    InterviewParticipantRole,
    InterviewSessionStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated API settings without reading local environment variables."""
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
    """Return one verified caller dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=roles,
            request_id="interview-lifecycle-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return request-scoped sessions bound to the isolated test database."""
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
    """Set the verified caller for one subsequent API request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


def _idempotency_headers() -> dict[str, str]:
    """Return a unique key for one lifecycle mutation."""
    return {"Idempotency-Key": str(uuid4())}


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one tenant required by foreign-key constrained fixtures."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Lifecycle API Tenant {tenant_id.hex[:12]}",
                slug=f"lifecycle-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_scheduled_interview(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    participant: User | None = None,
    start_at: datetime = datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
    end_at: datetime = datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
) -> tuple[InterviewSession, User]:
    """Create one scheduled interview and its reserved interviewer."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        if participant is None:
            participant = User(
                tenant_id=tenant_id,
                external_subject=f"interviewer-{uuid4().hex[:12]}",
                email=f"interviewer-{uuid4().hex[:12]}@example.test",
                display_name="Interview Participant",
            )
            session.add(participant)
            await session.flush()

        candidate = Candidate(
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{uuid4().hex[:12]}@example.test",
            normalized_email=f"ada-{uuid4().hex[:12]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="recruiter-subject",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="recruiter-subject",
        )
        session.add_all([candidate, requisition])
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.INTERVIEW,
            created_by_subject="recruiter-subject",
        )
        session.add(application)
        await session.flush()

        interview_session = InterviewSession(
            tenant_id=tenant_id,
            application_id=application.id,
            scheduled_start_at=start_at,
            scheduled_end_at=end_at,
            status=InterviewSessionStatus.SCHEDULED,
            created_by_subject="recruiter-subject",
        )
        session.add(interview_session)
        await session.flush()

        session.add(
            InterviewParticipant(
                tenant_id=tenant_id,
                interview_session_id=interview_session.id,
                user_id=participant.id,
                role=InterviewParticipantRole.INTERVIEWER,
                scheduled_time_range=Range(start_at, end_at, bounds="[)"),
            )
        )
        await session.flush()

        return interview_session, participant


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant used by the default lifecycle API caller."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with database and verified-caller overrides."""
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


@pytest.mark.asyncio
async def test_completes_session_idempotently_with_private_response(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Complete once and replay the persisted response for the same key."""
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _idempotency_headers()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/complete",
            json={"expected_version": 1},
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/complete",
            json={"expected_version": 1},
            headers=headers,
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "completed"
    assert first.json()["version"] == 2
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_cancels_session_with_controlled_reason(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Cancel a scheduled session only with a controlled reason."""
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/cancel",
            json={
                "expected_version": 1,
                "cancellation_reason": "candidate_unavailable",
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancellation_reason"] == "candidate_unavailable"
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_reschedules_session_and_rejects_stale_version(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Move a session with optimistic concurrency protection."""
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        moved = await client.put(
            f"/api/v1/interview-sessions/{interview_session.id}/schedule",
            json={
                "expected_version": 1,
                "scheduled_start_at": "2026-02-02T13:00:00Z",
                "scheduled_end_at": "2026-02-02T14:00:00Z",
            },
            headers=_idempotency_headers(),
        )
        stale = await client.put(
            f"/api/v1/interview-sessions/{interview_session.id}/schedule",
            json={
                "expected_version": 1,
                "scheduled_start_at": "2026-02-02T15:00:00Z",
                "scheduled_end_at": "2026-02-02T16:00:00Z",
            },
            headers=_idempotency_headers(),
        )

    assert moved.status_code == 200
    assert moved.json()["version"] == 2
    assert moved.json()["scheduled_start_at"] == "2026-02-02T13:00:00Z"
    assert moved.headers["Cache-Control"] == "private, no-store"

    assert stale.status_code == 409
    assert stale.json()["detail"] == (
        "Interview session has changed; retrieve the latest version and retry."
    )


@pytest.mark.asyncio
async def test_rejects_reschedule_that_double_books_participant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Map the PostgreSQL exclusion constraint to an HTTP conflict."""
    first_session, participant = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
        start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
    )
    await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
        participant=participant,
        start_at=datetime(2026, 2, 2, 11, 0, tzinfo=UTC),
        end_at=datetime(2026, 2, 2, 12, 0, tzinfo=UTC),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.put(
            f"/api/v1/interview-sessions/{first_session.id}/schedule",
            json={
                "expected_version": 1,
                "scheduled_start_at": "2026-02-02T11:30:00Z",
                "scheduled_end_at": "2026-02-02T12:30:00Z",
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "An interview participant is already booked."


@pytest.mark.asyncio
async def test_requires_lifecycle_authorization(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject interviewer-only callers from lifecycle management."""
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
    )
    _set_context(
        api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/complete",
            json={"expected_version": 1},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_hides_session_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Do not reveal another tenant's session existence."""
    owner_tenant_id = uuid4()
    await _create_tenant(database_engine, owner_tenant_id)
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=owner_tenant_id,
    )

    _set_context(
        api_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/cancel",
            json={
                "expected_version": 1,
                "cancellation_reason": "other",
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Interview session not found."


@pytest.mark.asyncio
async def test_rejects_unknown_fields_and_invalid_cancel_request(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject undeclared request fields and missing cancellation reasons."""
    interview_session, _ = await _seed_scheduled_interview(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        unknown_field = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/complete",
            json={
                "expected_version": 1,
                "unexpected_field": "must fail",
            },
            headers=_idempotency_headers(),
        )
        missing_reason = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/cancel",
            json={"expected_version": 1},
            headers=_idempotency_headers(),
        )

    assert unknown_field.status_code == 422
    assert missing_reason.status_code == 422
