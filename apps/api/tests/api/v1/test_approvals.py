"""HTTP integration tests for requisition approval endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import AnyHttpUrl
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant, User
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without requiring a local environment file."""
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


def _context_dependency(
    tenant_id: UUID,
    subject: str,
    roles: frozenset[Role],
) -> Callable[[], Awaitable[TenantContext]]:
    """Return a verified-caller dependency for one test request."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject=subject,
            roles=roles,
            request_id="test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped session dependency backed by the test database."""
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


def _idempotency_headers() -> dict[str, str]:
    """Return one unique idempotency header for a write request."""
    return {"Idempotency-Key": str(uuid4())}


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    subject: str,
    roles: frozenset[Role],
) -> None:
    """Replace the caller identity for the next request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject,
        roles,
    )


@pytest_asyncio.fixture(name="tenant_and_users")
async def tenant_and_users_fixture(
    database_engine: AsyncEngine,
) -> tuple[UUID, dict[str, UUID]]:
    """Create one tenant and users required by approval endpoint tests."""
    tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    subjects = (
        "tenant-admin",
        "recruiter",
        "approver-one",
        "approver-two",
        "unassigned-user",
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name="Approval API Test Tenant",
                slug=f"approval-api-{tenant_id.hex[:12]}",
            )
        )
        users = {
            subject: User(
                tenant_id=tenant_id,
                external_subject=subject,
                email=f"{subject}@example.test",
                display_name=subject.replace("-", " ").title(),
            )
            for subject in subjects
        }
        session.add_all(users.values())
        await session.flush()

        user_ids = {subject: user.id for subject, user in users.items()}

    return tenant_id, user_ids


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> AsyncIterator[FastAPI]:
    """Create an application with real services and overridden infrastructure."""
    tenant_id, _ = tenant_and_users
    application = create_app(_test_settings())

    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    _set_context(
        application,
        tenant_id=tenant_id,
        subject="tenant-admin",
        roles=frozenset({Role.TENANT_ADMIN}),
    )

    yield application

    application.dependency_overrides.clear()


async def _create_default_policy(
    client: AsyncClient,
    *,
    approver_user_ids: list[UUID],
) -> dict[str, Any]:
    """Create a default policy through the public API."""
    response = await client.post(
        "/api/v1/approval-policies",
        json={
            "name": "Default hiring approval",
            "approver_user_ids": [str(user_id) for user_id in approver_user_ids],
            "is_default": True,
        },
        headers=_idempotency_headers(),
    )

    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def _create_requisition(client: AsyncClient) -> dict[str, Any]:
    """Create one draft requisition through the public API."""
    response = await client.post(
        "/api/v1/requisitions",
        json={
            "title": "Senior Backend Engineer",
            "department": "Engineering",
            "headcount": 1,
        },
        headers=_idempotency_headers(),
    )

    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


async def _create_tenant(database_engine: AsyncEngine, tenant_id: UUID) -> None:
    """Create a tenant used to verify cross-tenant access isolation."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name="Other Approval API Tenant",
                slug=f"other-approval-api-{tenant_id.hex[:12]}",
            )
        )


@pytest.mark.asyncio
async def test_admin_creates_policy_and_replays_same_request(
    api_app: FastAPI,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> None:
    """Replay a repeated approval-policy creation request."""
    tenant_id, user_ids = tenant_and_users
    _set_context(
        api_app,
        tenant_id=tenant_id,
        subject="tenant-admin",
        roles=frozenset({Role.TENANT_ADMIN}),
    )
    transport = ASGITransport(app=api_app)
    headers = _idempotency_headers()
    payload = {
        "name": "Engineering approval",
        "approver_user_ids": [str(user_ids["approver-one"])],
        "is_default": True,
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/approval-policies",
            json=payload,
            headers=headers,
        )
        second = await client.post(
            "/api/v1/approval-policies",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"


@pytest.mark.asyncio
async def test_sequential_approvers_complete_requisition_approval(
    api_app: FastAPI,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> None:
    """Complete a multi-step approval through the public API."""
    tenant_id, user_ids = tenant_and_users
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="tenant-admin",
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        await _create_default_policy(
            client,
            approver_user_ids=[
                user_ids["approver-one"],
                user_ids["approver-two"],
            ],
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition = await _create_requisition(client)
        submission = await client.post(
            f"/api/v1/requisitions/{requisition['id']}/approval-submissions",
            headers=_idempotency_headers(),
        )

        approval_id = submission.json()["id"]

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-one",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        first_decision = await client.post(
            f"/api/v1/requisition-approvals/{approval_id}/approve",
            json={"comment": "Approved."},
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-two",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        second_decision = await client.post(
            f"/api/v1/requisition-approvals/{approval_id}/approve",
            json={},
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition_response = await client.get(
            f"/api/v1/requisitions/{requisition['id']}"
        )

    assert submission.status_code == 201
    assert first_decision.status_code == 200
    assert first_decision.json()["status"] == "pending"
    assert first_decision.json()["current_step"] == 2

    assert second_decision.status_code == 200
    assert second_decision.json()["status"] == "approved"

    assert requisition_response.status_code == 200
    assert requisition_response.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_rejection_returns_requisition_to_draft(
    api_app: FastAPI,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> None:
    """Return a requisition to draft when an approver rejects it."""
    tenant_id, user_ids = tenant_and_users
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="tenant-admin",
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        await _create_default_policy(
            client,
            approver_user_ids=[user_ids["approver-one"]],
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition = await _create_requisition(client)
        submission = await client.post(
            f"/api/v1/requisitions/{requisition['id']}/approval-submissions",
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-one",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        rejection = await client.post(
            f"/api/v1/requisition-approvals/{submission.json()['id']}/reject",
            json={"comment": "Budget is not approved."},
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition_response = await client.get(
            f"/api/v1/requisitions/{requisition['id']}"
        )

    assert rejection.status_code == 200
    assert rejection.json()["status"] == "rejected"
    assert requisition_response.json()["status"] == "draft"


@pytest.mark.asyncio
async def test_rejects_unauthorized_policy_and_decision_actions(
    api_app: FastAPI,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> None:
    """Reject policy and approval actions from unauthorized callers."""
    tenant_id, user_ids = tenant_and_users
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        policy_attempt = await client.post(
            "/api/v1/approval-policies",
            json={
                "name": "Unauthorized policy",
                "approver_user_ids": [str(user_ids["approver-one"])],
            },
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="tenant-admin",
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        await _create_default_policy(
            client,
            approver_user_ids=[user_ids["approver-one"]],
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition = await _create_requisition(client)
        submission = await client.post(
            f"/api/v1/requisitions/{requisition['id']}/approval-submissions",
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="unassigned-user",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        decision_attempt = await client.post(
            f"/api/v1/requisition-approvals/{submission.json()['id']}/approve",
            json={},
            headers=_idempotency_headers(),
        )

    assert policy_attempt.status_code == 403
    assert decision_attempt.status_code == 403


@pytest.mark.asyncio
async def test_hides_approval_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_and_users: tuple[UUID, dict[str, UUID]],
) -> None:
    """Hide approval records from callers in another tenant."""
    tenant_id, user_ids = tenant_and_users
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="tenant-admin",
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        await _create_default_policy(
            client,
            approver_user_ids=[user_ids["approver-one"]],
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="recruiter",
            roles=frozenset({Role.RECRUITER}),
        )
        requisition = await _create_requisition(client)
        submission = await client.post(
            f"/api/v1/requisitions/{requisition['id']}/approval-submissions",
            headers=_idempotency_headers(),
        )

        other_tenant_id = uuid4()
        await _create_tenant(database_engine, other_tenant_id)

        _set_context(
            api_app,
            tenant_id=other_tenant_id,
            subject="unknown-user",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        response = await client.post(
            f"/api/v1/requisition-approvals/{submission.json()['id']}/approve",
            json={},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 404
