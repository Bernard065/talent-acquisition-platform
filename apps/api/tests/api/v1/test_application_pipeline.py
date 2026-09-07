"""HTTP integration tests for application pipeline transition endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
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
from app.db.models.application_stage_history import ApplicationStageHistory
from app.db.models.audit import AuditEvent
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
    """Build isolated settings without reading the local environment file."""
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
            subject="recruiter-subject",
            roles=roles,
            request_id="application-pipeline-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return request-scoped async sessions bound to the test database."""
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
    """Set the verified caller for a subsequent ASGI request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


def _idempotency_headers() -> dict[str, str]:
    """Create a unique idempotency key for one mutation."""
    return {"Idempotency-Key": str(uuid4())}


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one tenant for an application fixture."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Pipeline API Tenant {tenant_id.hex[:12]}",
                slug=f"pipeline-api-{tenant_id.hex[:12]}",
            )
        )


async def _create_applied_application(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> Application:
    """Seed one applied application and its immutable initial history entry."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    candidate_id = uuid4()
    requisition_id = uuid4()

    async with session_factory.begin() as session:
        session.add(
            Candidate(
                id=candidate_id,
                tenant_id=tenant_id,
                full_name="Ada Lovelace",
                email=f"ada-{candidate_id.hex[:10]}@example.test",
                normalized_email=f"ada-{candidate_id.hex[:10]}@example.test",
                source="employee_referral",
                source_metadata={},
                consent_status=CandidateConsentStatus.UNKNOWN,
                created_by_subject="recruiter-subject",
            )
        )
        session.add(
            Requisition(
                id=requisition_id,
                tenant_id=tenant_id,
                title="Senior Backend Engineer",
                headcount=1,
                status=RequisitionStatus.OPEN,
                created_by_subject="recruiter-subject",
            )
        )
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            requisition_id=requisition_id,
            status=ApplicationStatus.APPLIED,
            created_by_subject="recruiter-subject",
        )
        session.add(application)
        await session.flush()

        session.add(
            ApplicationStageHistory(
                tenant_id=tenant_id,
                application_id=application.id,
                from_status=None,
                to_status=ApplicationStatus.APPLIED,
                transitioned_by_subject="recruiter-subject",
                transitioned_at=datetime.now(UTC),
            )
        )
        await session.flush()

        return application


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default tenant used by pipeline endpoint tests."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="pipeline_app")
async def pipeline_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create an application with verified identity and DB overrides."""
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
async def test_transitions_application_idempotently_and_records_history_and_audit(
    pipeline_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Persist one stage change and replay its exact response for the same key."""
    application = await _create_applied_application(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _idempotency_headers()
    payload = {
        "target_status": "screening",
        "expected_version": 1,
    }

    async with AsyncClient(
        transport=ASGITransport(app=pipeline_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json=payload,
            headers=headers,
        )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        histories = list(
            await session.scalars(
                select(ApplicationStageHistory).where(
                    ApplicationStageHistory.application_id == application.id
                )
            )
        )
        audit_event = await session.scalar(
            select(AuditEvent).where(
                AuditEvent.entity_id == str(application.id),
                AuditEvent.action == "application.stage_changed",
            )
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["status"] == "screening"
    assert first.json()["version"] == 2
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"

    assert len(histories) == 2
    assert any(
        history.from_status is ApplicationStatus.APPLIED
        and history.to_status is ApplicationStatus.SCREENING
        for history in histories
    )
    assert audit_event is not None
    assert audit_event.details["target_status"] == "screening"


@pytest.mark.asyncio
async def test_requires_rejection_reason(
    pipeline_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject a rejected-stage request with no controlled reason."""
    application = await _create_applied_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=pipeline_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json={
                "target_status": "rejected",
                "expected_version": 1,
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_stale_application_version(
    pipeline_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Require a caller to transition the current application version."""
    application = await _create_applied_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=pipeline_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json={
                "target_status": "screening",
                "expected_version": 2,
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Application has changed; retrieve the latest version and retry."
    )


@pytest.mark.asyncio
async def test_requires_pipeline_authorization(
    pipeline_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject transitions from roles without pipeline write access."""
    application = await _create_applied_application(
        database_engine,
        tenant_id=tenant_id,
    )
    _set_context(
        pipeline_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.INTERVIEWER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=pipeline_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json={
                "target_status": "screening",
                "expected_version": 1,
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission."


@pytest.mark.asyncio
async def test_hides_application_from_another_tenant(
    pipeline_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Return not-found without revealing another tenant's application."""
    owner_tenant_id = uuid4()
    await _create_tenant(database_engine, owner_tenant_id)
    application = await _create_applied_application(
        database_engine,
        tenant_id=owner_tenant_id,
    )

    _set_context(
        pipeline_app,
        tenant_id=tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )

    async with AsyncClient(
        transport=ASGITransport(app=pipeline_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/applications/{application.id}/stage-transitions",
            json={
                "target_status": "screening",
                "expected_version": 1,
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate or application not found."
