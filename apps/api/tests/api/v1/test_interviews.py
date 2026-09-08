"""HTTP integration tests for interview scheduling."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.application import Application
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.interview import InterviewSession
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import (
    ApplicationStatus,
    CandidateConsentStatus,
)
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated API settings without using local environment variables."""
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
    """Return a verified caller override for one request context."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=roles,
            request_id="interview-api-test-request-id",
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
    """Set the verified caller for a subsequent test request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


def _idempotency_headers() -> dict[str, str]:
    """Return a fresh key for one write operation."""
    return {"Idempotency-Key": str(uuid4())}


def _payload(interviewer_id: UUID) -> dict[str, object]:
    """Build a valid schedule request without PII."""
    return {
        "scheduled_start_at": "2026-02-02T09:00:00Z",
        "scheduled_end_at": "2026-02-02T10:00:00Z",
        "participants": [
            {
                "user_id": str(interviewer_id),
                "role": "interviewer",
            }
        ],
    }


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist a tenant needed by foreign-key constrained fixtures."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Interview API Tenant {tenant_id.hex[:12]}",
                slug=f"interview-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_interview_data(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    application_status: ApplicationStatus = ApplicationStatus.INTERVIEW,
    application_count: int = 1,
) -> tuple[list[Application], User]:
    """Seed one tenant's interviewer and interview applications."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        interviewer = User(
            tenant_id=tenant_id,
            external_subject=f"interviewer-{tenant_id.hex[:12]}",
            email=f"interviewer-{tenant_id.hex[:12]}@example.test",
            display_name="Interview Panel Member",
        )
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=RequisitionStatus.OPEN,
            created_by_subject="recruiter-subject",
        )
        session.add_all([interviewer, requisition])
        await session.flush()

        applications: list[Application] = []

        for index in range(application_count):
            candidate = Candidate(
                tenant_id=tenant_id,
                full_name=f"Candidate {index}",
                email=f"candidate-{tenant_id.hex[:12]}-{index}@example.test",
                normalized_email=(
                    f"candidate-{tenant_id.hex[:12]}-{index}@example.test"
                ),
                source="employee_referral",
                source_metadata={},
                consent_status=CandidateConsentStatus.UNKNOWN,
                created_by_subject="recruiter-subject",
            )
            session.add(candidate)
            await session.flush()

            application = Application(
                tenant_id=tenant_id,
                candidate_id=candidate.id,
                requisition_id=requisition.id,
                status=application_status,
                created_by_subject="recruiter-subject",
            )
            session.add(application)
            applications.append(application)

        await session.flush()
        return applications, interviewer


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant used by interview endpoint tests."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with verified identity and DB dependency overrides."""
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
async def test_schedules_interview_idempotently_and_returns_private_response(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one interview and replay its exact response for the same key."""
    applications, interviewer = await _seed_interview_data(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _idempotency_headers()
    payload = _payload(interviewer.id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=payload,
            headers=headers,
        )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        interview_count = len(
            list(
                await session.scalars(
                    select(InterviewSession).where(
                        InterviewSession.application_id == applications[0].id
                    )
                )
            )
        )
        audit_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "interview_session.scheduled"
            )
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json() == replay.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert interview_count == 1
    assert audit_event is not None


@pytest.mark.asyncio
async def test_requires_application_to_be_in_interview_stage(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject scheduling when the application is not interview-ready."""
    applications, interviewer = await _seed_interview_data(
        database_engine,
        tenant_id=tenant_id,
        application_status=ApplicationStatus.SCREENING,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=_payload(interviewer.id),
            headers=_idempotency_headers(),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid interview scheduling request."


@pytest.mark.asyncio
async def test_requires_interview_scheduling_authorization(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject interviewers who are not allowed to schedule interviews."""
    applications, interviewer = await _seed_interview_data(
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
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=_payload(interviewer.id),
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_hides_application_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Return not-found without revealing another tenant's application."""
    owner_tenant_id = uuid4()
    await _create_tenant(database_engine, owner_tenant_id)
    applications, interviewer = await _seed_interview_data(
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
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=_payload(interviewer.id),
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate or application not found."


@pytest.mark.asyncio
async def test_hides_participant_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Avoid exposing whether a participant exists in another tenant."""
    applications, _ = await _seed_interview_data(
        database_engine,
        tenant_id=tenant_id,
    )

    other_tenant_id = uuid4()
    await _create_tenant(database_engine, other_tenant_id)
    _, other_tenant_interviewer = await _seed_interview_data(
        database_engine,
        tenant_id=other_tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=_payload(other_tenant_interviewer.id),
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Interview application or participant not found."


@pytest.mark.asyncio
async def test_returns_conflict_for_overlapping_interviewer_booking(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Map the PostgreSQL exclusion constraint to a safe HTTP conflict."""
    applications, interviewer = await _seed_interview_data(
        database_engine,
        tenant_id=tenant_id,
        application_count=2,
    )
    first_payload = _payload(interviewer.id)
    second_start = datetime(2026, 2, 2, 9, 30, tzinfo=UTC)
    second_end = second_start + timedelta(hours=1)
    second_payload = {
        **_payload(interviewer.id),
        "scheduled_start_at": second_start.isoformat(),
        "scheduled_end_at": second_end.isoformat(),
    }

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/applications/{applications[0].id}/interviews",
            json=first_payload,
            headers=_idempotency_headers(),
        )
        conflicting = await client.post(
            f"/api/v1/applications/{applications[1].id}/interviews",
            json=second_payload,
            headers=_idempotency_headers(),
        )

    assert first.status_code == 201
    assert conflicting.status_code == 409
    assert conflicting.json()["detail"] == "An interview participant is already booked."
