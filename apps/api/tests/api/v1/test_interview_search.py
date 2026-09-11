"""HTTP integration tests for private interview calendar search."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
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
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _context_dependency(
    tenant_id: UUID,
    *,
    subject: str,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Build a verified caller dependency override."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject=subject,
            roles=roles,
            request_id="interview-search-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build request-scoped sessions against the isolated database."""
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
    subject: str = "recruiter-subject",
    roles: frozenset[Role] = frozenset({Role.RECRUITER}),
) -> None:
    """Set the verified caller used by following API requests."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject=subject,
        roles=roles,
    )


async def _seed_interviews(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    prefix: str,
) -> tuple[list[InterviewSession], dict[str, User]]:
    """Persist a tenant interview calendar with two interviewers."""
    now = datetime.now(UTC).replace(microsecond=0)
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Interview API Tenant {prefix}",
                slug=f"interview-api-{prefix}-{tenant_id.hex[:8]}",
            )
        )
        await session.flush()

        users = {
            "interviewer_one": User(
                tenant_id=tenant_id,
                external_subject="interviewer-one-subject",
                email=f"one-{prefix}-{tenant_id.hex[:8]}@example.test",
                display_name="Interviewer One",
            ),
            "interviewer_two": User(
                tenant_id=tenant_id,
                external_subject="interviewer-two-subject",
                email=f"two-{prefix}-{tenant_id.hex[:8]}@example.test",
                display_name="Interviewer Two",
            ),
        }
        session.add_all(users.values())

        candidate = Candidate(
            tenant_id=tenant_id,
            full_name=f"Ada Lovelace {prefix}",
            email=f"ada-{prefix}-{tenant_id.hex[:8]}@example.test",
            normalized_email=f"ada-{prefix}-{tenant_id.hex[:8]}@example.test",
            source="public_job",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
            created_by_subject="seed",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
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
            status=ApplicationStatus.INTERVIEW,
            created_by_subject="seed",
        )
        session.add(application)
        await session.flush()

        sessions = [
            InterviewSession(
                tenant_id=tenant_id,
                application_id=application.id,
                scheduled_start_at=now + timedelta(hours=3),
                scheduled_end_at=now + timedelta(hours=4),
                status=InterviewSessionStatus.SCHEDULED,
                created_by_subject="recruiter-subject",
            ),
            InterviewSession(
                tenant_id=tenant_id,
                application_id=application.id,
                scheduled_start_at=now + timedelta(hours=2),
                scheduled_end_at=now + timedelta(hours=3),
                status=InterviewSessionStatus.COMPLETED,
                completed_at=now + timedelta(hours=3),
                created_by_subject="recruiter-subject",
            ),
            InterviewSession(
                tenant_id=tenant_id,
                application_id=application.id,
                scheduled_start_at=now + timedelta(hours=1),
                scheduled_end_at=now + timedelta(hours=2),
                status=InterviewSessionStatus.SCHEDULED,
                created_by_subject="recruiter-subject",
            ),
        ]
        session.add_all(sessions)
        await session.flush()

        session.add_all(
            [
                InterviewParticipant(
                    tenant_id=tenant_id,
                    interview_session_id=sessions[0].id,
                    user_id=users["interviewer_one"].id,
                    role=InterviewParticipantRole.INTERVIEWER,
                    scheduled_time_range=Range(
                        sessions[0].scheduled_start_at,
                        sessions[0].scheduled_end_at,
                        bounds="[)",
                    ),
                ),
                InterviewParticipant(
                    tenant_id=tenant_id,
                    interview_session_id=sessions[1].id,
                    user_id=users["interviewer_two"].id,
                    role=InterviewParticipantRole.INTERVIEWER,
                    scheduled_time_range=Range(
                        sessions[1].scheduled_start_at,
                        sessions[1].scheduled_end_at,
                        bounds="[)",
                    ),
                ),
                InterviewParticipant(
                    tenant_id=tenant_id,
                    interview_session_id=sessions[2].id,
                    user_id=users["interviewer_one"].id,
                    role=InterviewParticipantRole.INTERVIEWER,
                    scheduled_time_range=Range(
                        sessions[2].scheduled_start_at,
                        sessions[2].scheduled_end_at,
                        bounds="[)",
                    ),
                ),
            ]
        )
        await session.flush()

        return sessions, users


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture() -> UUID:
    """Return the default tenant identifier for the API caller."""
    return uuid4()


@pytest_asyncio.fixture(name="interview_search_app")
async def interview_search_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with test database and caller overrides."""
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
async def test_recruiter_filters_calendar_and_receives_private_safe_response(
    interview_search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Recruiters can filter tenant sessions without feedback leakage."""
    sessions, users = await _seed_interviews(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=interview_search_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/interviews",
            params={
                "participant_user_id": str(users["interviewer_one"].id),
                "status": "scheduled",
            },
        )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [item["id"] for item in response.json()["items"]] == [
        str(sessions[0].id),
        str(sessions[2].id),
    ]

    serialized = str(response.json()).lower()
    assert "feedback" not in serialized
    assert "recommendation" not in serialized
    assert "score" not in serialized
    assert {
        item["participants"][0]["user_id"]
        for item in response.json()["items"]
    } == {str(users["interviewer_one"].id)}


@pytest.mark.asyncio
async def test_interviewer_can_view_only_own_calendar(
    interview_search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Interviewer access is restricted to assigned interview sessions."""
    sessions, users = await _seed_interviews(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )
    _set_context(
        interview_search_app,
        tenant_id=tenant_id,
        subject="interviewer-one-subject",
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=interview_search_app),
        base_url="http://testserver",
    ) as client:
        own_calendar = await client.get("/api/v1/interviews")
        forbidden_filter = await client.get(
            "/api/v1/interviews",
            params={
                "participant_user_id": str(users["interviewer_two"].id),
            },
        )

    assert own_calendar.status_code == 200
    assert [item["id"] for item in own_calendar.json()["items"]] == [
        str(sessions[0].id),
        str(sessions[2].id),
    ]
    assert forbidden_filter.status_code == 403


@pytest.mark.asyncio
async def test_calendar_cursor_pagination_and_tenant_isolation(
    interview_search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Pages are stable and a caller cannot discover another tenant's sessions."""
    sessions, _ = await _seed_interviews(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    other_tenant_id = uuid4()
    other_sessions, _ = await _seed_interviews(
        database_engine,
        tenant_id=other_tenant_id,
        prefix="other",
    )

    async with AsyncClient(
        transport=ASGITransport(app=interview_search_app),
        base_url="http://testserver",
    ) as client:
        first_page = await client.get(
            "/api/v1/interviews",
            params={"limit": 2},
        )
        second_page = await client.get(
            "/api/v1/interviews",
            params={
                "limit": 2,
                "cursor": first_page.json()["next_cursor"],
            },
        )
        hidden = await client.get(
            "/api/v1/interviews",
            params={"application_id": str(other_sessions[0].application_id)},
        )

    returned_ids = [
        item["id"]
        for item in first_page.json()["items"] + second_page.json()["items"]
    ]

    assert returned_ids == [
        str(sessions[0].id),
        str(sessions[1].id),
        str(sessions[2].id),
    ]
    assert len(returned_ids) == len(set(returned_ids))
    assert second_page.json()["next_cursor"] is None
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []


@pytest.mark.asyncio
async def test_rejects_malformed_interview_cursor(
    interview_search_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Malformed calendar pagination state maps to a safe validation response."""
    await _seed_interviews(
        database_engine,
        tenant_id=tenant_id,
        prefix="owner",
    )

    async with AsyncClient(
        transport=ASGITransport(app=interview_search_app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/interviews",
            params={"cursor": "not-a-valid-cursor"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid interview search cursor."
