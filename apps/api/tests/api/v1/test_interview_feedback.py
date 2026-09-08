"""HTTP integration tests for private interviewer feedback endpoints."""

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
    """Build isolated settings without reading local environment variables."""
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
    subject: str,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return one verified caller dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject=subject,
            roles=roles,
            request_id="interview-feedback-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return request-scoped sessions bound to the test database."""
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
    subject: str,
    roles: frozenset[Role],
) -> None:
    """Set the verified caller for a subsequent request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject,
        roles,
    )


def _idempotency_headers() -> dict[str, str]:
    """Return a unique idempotency key for one write operation."""
    return {"Idempotency-Key": str(uuid4())}


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create one tenant required by test fixtures."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Feedback API Tenant {tenant_id.hex[:12]}",
                slug=f"feedback-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_interview_session(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> tuple[InterviewSession, User, User]:
    """Create a completed interview with two assigned interviewers."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        author = User(
            tenant_id=tenant_id,
            external_subject="author-subject",
            email=f"author-{tenant_id.hex[:12]}@example.test",
            display_name="Feedback Author",
        )
        other_interviewer = User(
            tenant_id=tenant_id,
            external_subject="other-interviewer-subject",
            email=f"other-{tenant_id.hex[:12]}@example.test",
            display_name="Other Interviewer",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="recruiter-subject",
        )
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:12]}@example.test",
            normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.UNKNOWN,
            created_by_subject="recruiter-subject",
        )
        session.add_all([author, other_interviewer, requisition, candidate])
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
            scheduled_start_at=datetime(2026, 2, 2, 9, 0, tzinfo=UTC),
            scheduled_end_at=datetime(2026, 2, 2, 10, 0, tzinfo=UTC),
            status=InterviewSessionStatus.COMPLETED,
            completed_at=datetime(2026, 2, 2, 10, 30, tzinfo=UTC),
            created_by_subject="recruiter-subject",
        )
        session.add(interview_session)
        await session.flush()

        for interviewer in (author, other_interviewer):
            session.add(
                InterviewParticipant(
                    tenant_id=tenant_id,
                    interview_session_id=interview_session.id,
                    user_id=interviewer.id,
                    role=InterviewParticipantRole.INTERVIEWER,
                    scheduled_time_range=Range(
                        interview_session.scheduled_start_at,
                        interview_session.scheduled_end_at,
                        bounds="[)",
                    ),
                )
            )

        await session.flush()
        return interview_session, author, other_interviewer


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant used by endpoint tests."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with DB and verified identity dependency overrides."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    _set_context(
        application,
        tenant_id=tenant_id,
        subject="author-subject",
        roles=frozenset({Role.INTERVIEWER}),
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


async def _create_draft(
    client: AsyncClient,
    interview_session_id: UUID,
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, object]:
    """Create one feedback draft through the HTTP API."""
    response = await client.post(
        f"/api/v1/interview-sessions/{interview_session_id}/feedback",
        json={
            "overall_rating": 4,
            "recommendation": "yes",
            "strengths": "Clear systems-design reasoning.",
            "concerns": None,
        },
        headers=headers or _idempotency_headers(),
    )

    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_creates_and_replays_private_feedback_draft(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Replay the exact response without creating a second feedback draft."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _idempotency_headers()
    payload = {
        "overall_rating": 4,
        "recommendation": "yes",
        "strengths": "Clear systems-design reasoning.",
        "concerns": None,
    }

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/feedback",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/feedback",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json() == replay.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_only_author_can_read_or_modify_feedback(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Prevent another assigned interviewer from viewing or altering feedback."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        draft = await _create_draft(client, interview_session.id)

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="other-interviewer-subject",
            roles=frozenset({Role.INTERVIEWER}),
        )

        read_response = await client.get(
            f"/api/v1/interview-feedback/{draft['id']}"
        )
        update_response = await client.put(
            f"/api/v1/interview-feedback/{draft['id']}",
            json={
                "expected_version": 1,
                "overall_rating": 1,
                "recommendation": "strong_no",
                "strengths": None,
                "concerns": "Not the author.",
            },
            headers=_idempotency_headers(),
        )

    assert read_response.status_code == 404
    assert update_response.status_code == 404


@pytest.mark.asyncio
async def test_hides_feedback_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Return not-found without revealing cross-tenant feedback existence."""
    owner_tenant_id = uuid4()
    await _create_tenant(database_engine, owner_tenant_id)
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=owner_tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        _set_context(
            api_app,
            tenant_id=owner_tenant_id,
            subject="author-subject",
            roles=frozenset({Role.INTERVIEWER}),
        )
        draft = await _create_draft(client, interview_session.id)

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="author-subject",
            roles=frozenset({Role.INTERVIEWER}),
        )
        response = await client.get(
            f"/api/v1/interview-feedback/{draft['id']}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Interview feedback not found."


@pytest.mark.asyncio
async def test_updates_draft_and_rejects_stale_version(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Require versioned replacement of feedback draft content."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        draft = await _create_draft(client, interview_session.id)

        updated = await client.put(
            f"/api/v1/interview-feedback/{draft['id']}",
            json={
                "expected_version": 1,
                "overall_rating": 5,
                "recommendation": "strong_yes",
                "strengths": "Strong technical depth.",
                "concerns": None,
            },
            headers=_idempotency_headers(),
        )
        stale = await client.put(
            f"/api/v1/interview-feedback/{draft['id']}",
            json={
                "expected_version": 1,
                "overall_rating": 3,
                "recommendation": "yes",
                "strengths": None,
                "concerns": "Stale update.",
            },
            headers=_idempotency_headers(),
        )

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["overall_rating"] == 5
    assert updated.headers["Cache-Control"] == "private, no-store"

    assert stale.status_code == 409
    assert stale.json()["detail"] == (
        "Interview feedback has changed; retrieve the latest version and retry."
    )


@pytest.mark.asyncio
async def test_submits_idempotently_and_prevents_later_updates(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Submit once, replay safely, and reject edits after submission."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )
    submit_headers = _idempotency_headers()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        draft = await _create_draft(client, interview_session.id)

        submit_payload = {
            "expected_version": 1,
            "overall_rating": 5,
            "recommendation": "strong_yes",
            "strengths": "Excellent communication.",
            "concerns": None,
        }
        first_submit = await client.post(
            f"/api/v1/interview-feedback/{draft['id']}/submit",
            json=submit_payload,
            headers=submit_headers,
        )
        replay_submit = await client.post(
            f"/api/v1/interview-feedback/{draft['id']}/submit",
            json=submit_payload,
            headers=submit_headers,
        )
        update = await client.put(
            f"/api/v1/interview-feedback/{draft['id']}",
            json={
                "expected_version": 2,
                "overall_rating": 1,
                "recommendation": "strong_no",
                "strengths": None,
                "concerns": "Attempted edit after submission.",
            },
            headers=_idempotency_headers(),
        )

    assert first_submit.status_code == 200
    assert replay_submit.status_code == 200
    assert first_submit.json() == replay_submit.json()
    assert first_submit.json()["status"] == "submitted"
    assert first_submit.headers["Idempotent-Replayed"] == "false"
    assert replay_submit.headers["Idempotent-Replayed"] == "true"

    assert update.status_code == 409
    assert update.json()["detail"] == (
        "Interview feedback cannot be changed in its current state."
    )


@pytest.mark.asyncio
async def test_requires_interviewer_role(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject callers without the interviewer role."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )
    _set_context(
        api_app,
        tenant_id=tenant_id,
        subject="author-subject",
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/feedback",
            json={},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_rejects_unknown_feedback_fields(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject undeclared fields instead of silently ignoring them."""
    interview_session, _, _ = await _seed_interview_session(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/interview-sessions/{interview_session.id}/feedback",
            json={"unexpected_field": "must fail"},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 422
