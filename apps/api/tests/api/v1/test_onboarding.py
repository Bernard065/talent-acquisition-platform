"""HTTP integration tests for private onboarding workflow endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
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
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.onboarding import OnboardingTask
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
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
            request_id="onboarding-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build request-scoped sessions for the isolated test database."""
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
    subject: str = "people-operations-subject",
    roles: frozenset[Role] = frozenset({Role.PEOPLE_OPERATIONS}),
) -> None:
    """Set the verified caller for a following API request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject=subject,
        roles=roles,
    )


def _headers() -> dict[str, str]:
    """Return a unique idempotency key for one mutation."""
    return {"Idempotency-Key": str(uuid4())}


def _template_payload(*, task_count: int = 1) -> dict[str, object]:
    """Build a valid onboarding template payload."""
    return {
        "name": "Standard employee onboarding",
        "version": 1,
        "tasks": [
            {
                "title": f"Onboarding task {position}",
                "description": f"Complete onboarding step {position}.",
                "due_offset_days": position,
                "default_assignee_role": "people_operations",
            }
            for position in range(1, task_count + 1)
        ],
    }


async def _create_tenant(engine: AsyncEngine, tenant_id: UUID) -> None:
    """Create one foreign-key parent tenant."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Onboarding API Tenant {tenant_id.hex[:12]}",
                slug=f"onboarding-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_hired_application(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> tuple[Application, User]:
    """Create a hired application and a tenant-owned task assignee."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        people_operations = User(
            tenant_id=tenant_id,
            external_subject="people-operations-subject",
            email=f"peopleops-{tenant_id.hex[:12]}@example.test",
            display_name="People Operations",
        )
        assignee = User(
            tenant_id=tenant_id,
            external_subject="assignee-subject",
            email=f"assignee-{tenant_id.hex[:12]}@example.test",
            display_name="Task Assignee",
        )
        candidate = Candidate(
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:12]}@example.test",
            normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
            source="employee_referral",
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
        session.add_all(
            [
                people_operations,
                assignee,
                candidate,
                requisition,
            ]
        )
        await session.flush()

        application = Application(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            requisition_id=requisition.id,
            status=ApplicationStatus.HIRED,
            created_by_subject="seed",
        )
        session.add(application)
        await session.flush()

        return application, assignee


async def _instance_task_ids(
    engine: AsyncEngine,
    instance_id: UUID,
) -> list[UUID]:
    """Read instantiated task IDs because this branch has no read endpoint."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        return list(
            await session.scalars(
                select(OnboardingTask.id)
                .where(OnboardingTask.onboarding_instance_id == instance_id)
                .order_by(OnboardingTask.created_at)
            )
        )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default API caller tenant."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with database and verified-identity overrides."""
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
async def test_creates_template_idempotently_with_private_response(
    api_app: FastAPI,
) -> None:
    """Persist one template and replay the exact response for the same key."""
    headers = _headers()
    payload = _template_payload()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            "/api/v1/onboarding-templates",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            "/api/v1/onboarding-templates",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["name"] == "Standard employee onboarding"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"


@pytest.mark.asyncio
async def test_starts_assigns_updates_and_completes_onboarding(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Exercise the full onboarding workflow through private endpoints."""
    application, assignee = await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        template = await client.post(
            "/api/v1/onboarding-templates",
            json=_template_payload(),
            headers=_headers(),
        )
        template_id = template.json()["id"]

        started = await client.post(
            f"/api/v1/applications/{application.id}/onboarding-instances",
            json={"onboarding_template_id": template_id},
            headers=_headers(),
        )
        instance_id = UUID(started.json()["id"])
        task_id = (await _instance_task_ids(database_engine, instance_id))[0]

        assigned = await client.post(
            f"/api/v1/onboarding-tasks/{task_id}/assignee",
            json={
                "assignee_user_id": str(assignee.id),
                "expected_task_version": 1,
            },
            headers=_headers(),
        )
        in_progress = await client.patch(
            f"/api/v1/onboarding-tasks/{task_id}/status",
            json={
                "expected_version": 2,
                "target_status": "in_progress",
            },
            headers=_headers(),
        )
        completed_task = await client.patch(
            f"/api/v1/onboarding-tasks/{task_id}/status",
            json={
                "expected_version": 3,
                "target_status": "completed",
            },
            headers=_headers(),
        )
        completed_instance = await client.post(
            f"/api/v1/onboarding-instances/{instance_id}/complete",
            json={"expected_instance_version": 1},
            headers=_headers(),
        )

    assert template.status_code == 201
    assert started.status_code == 201
    assert started.json()["status"] == "active"
    assert assigned.status_code == 200
    assert assigned.json()["assignee_user_id"] == str(assignee.id)
    assert in_progress.status_code == 200
    assert in_progress.json()["status"] == "in_progress"
    assert completed_task.status_code == 200
    assert completed_task.json()["status"] == "completed"
    assert completed_instance.status_code == 200
    assert completed_instance.json()["status"] == "completed"
    assert completed_instance.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_replays_task_status_update_and_rejects_stale_version(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Use durable replay while rejecting a different stale request."""
    application, _ = await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        template = await client.post(
            "/api/v1/onboarding-templates",
            json=_template_payload(),
            headers=_headers(),
        )
        started = await client.post(
            f"/api/v1/applications/{application.id}/onboarding-instances",
            json={"onboarding_template_id": template.json()["id"]},
            headers=_headers(),
        )
        task_id = (await _instance_task_ids(
            database_engine,
            UUID(started.json()["id"]),
        ))[0]

        headers = _headers()
        payload = {
            "expected_version": 1,
            "target_status": "in_progress",
        }
        first = await client.patch(
            f"/api/v1/onboarding-tasks/{task_id}/status",
            json=payload,
            headers=headers,
        )
        replay = await client.patch(
            f"/api/v1/onboarding-tasks/{task_id}/status",
            json=payload,
            headers=headers,
        )
        stale = await client.patch(
            f"/api/v1/onboarding-tasks/{task_id}/status",
            json={
                "expected_version": 1,
                "target_status": "blocked",
                "blocked_reason": "Awaiting access.",
            },
            headers=_headers(),
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_cancels_active_onboarding(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Cancel active onboarding through the private lifecycle endpoint."""
    application, _ = await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        template = await client.post(
            "/api/v1/onboarding-templates",
            json=_template_payload(task_count=2),
            headers=_headers(),
        )
        started = await client.post(
            f"/api/v1/applications/{application.id}/onboarding-instances",
            json={"onboarding_template_id": template.json()["id"]},
            headers=_headers(),
        )
        cancelled = await client.post(
            f"/api/v1/onboarding-instances/{started.json()['id']}/cancel",
            json={"expected_instance_version": 1},
            headers=_headers(),
        )

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["cancelled_at"] is not None
    assert cancelled.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_enforces_authorization_tenant_isolation_and_strict_fields(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject unauthorized callers, unknown fields, and cross-tenant access."""
    application, _ = await _seed_hired_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        unknown_field = await client.post(
            "/api/v1/onboarding-templates",
            json={**_template_payload(), "unexpected_field": True},
            headers=_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            roles=frozenset({Role.INTERVIEWER}),
        )
        forbidden = await client.post(
            f"/api/v1/applications/{application.id}/onboarding-instances",
            json={"onboarding_template_id": str(uuid4())},
            headers=_headers(),
        )

        owner_tenant_id = uuid4()
        await _create_tenant(database_engine, owner_tenant_id)
        owner_application, _ = await _seed_hired_application(
            database_engine,
            tenant_id=owner_tenant_id,
        )

        _set_context(api_app, tenant_id=owner_tenant_id)
        owner_template = await client.post(
            "/api/v1/onboarding-templates",
            json=_template_payload(),
            headers=_headers(),
        )
        owner_instance = await client.post(
            f"/api/v1/applications/{owner_application.id}/onboarding-instances",
            json={"onboarding_template_id": owner_template.json()["id"]},
            headers=_headers(),
        )

        _set_context(api_app, tenant_id=tenant_id)
        hidden = await client.post(
            f"/api/v1/onboarding-instances/{owner_instance.json()['id']}/cancel",
            json={"expected_instance_version": 1},
            headers=_headers(),
        )

    assert unknown_field.status_code == 422
    assert forbidden.status_code == 403
    assert hidden.status_code == 404
