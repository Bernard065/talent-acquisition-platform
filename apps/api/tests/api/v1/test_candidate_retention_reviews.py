"""HTTP integration coverage for private candidate retention-review endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
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
from app.db.models.audit import AuditEvent
from app.db.models.candidate import Candidate
from app.db.models.candidate_retention_policy import CandidateRetentionPolicy
from app.db.models.candidate_retention_review import CandidateRetentionReview
from app.db.models.identity import Tenant
from app.domains.candidates.enums import CandidatePrivacyStatus
from app.domains.candidates.retention_enums import CandidateRetentionPolicyStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build test settings without reading a local environment file."""
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
    """Override authentication with one trusted test identity."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="retention-review-test-subject",
            roles=roles,
            request_id="retention-review-test-request",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide request-scoped sessions bound to the isolated test database."""
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
    """Change the trusted tenant and roles for the next request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


@pytest_asyncio.fixture(name="retention_tenant_id")
async def retention_tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant used by retention-review endpoint tests."""
    tenant_id = uuid4()
    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name="Retention Review API Tenant",
                slug=f"retention-api-{tenant_id.hex[:12]}",
            )
        )
    return tenant_id


@pytest_asyncio.fixture(name="retention_api_app")
async def retention_api_app_fixture(
    database_engine: AsyncEngine,
    retention_tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Override only database access and the verified tenant context."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(database_engine)
    _set_context(
        application,
        tenant_id=retention_tenant_id,
        roles=frozenset({Role.RECRUITER}),
    )
    yield application
    application.dependency_overrides.clear()
    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE audit_events, requisitions, "
                "user_role_assignments, users, tenants CASCADE"
            )
        )


async def _create_candidate(client: AsyncClient) -> dict[str, Any]:
    """Create a candidate using the existing authenticated candidate API."""
    response = await client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Private Review Candidate",
            "email": "private.review.candidate@example.test",
            "source": "direct",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    return response.json()


async def _create_active_policy(
    database_engine: AsyncEngine,
    *,
    tenant_id: UUID,
) -> CandidateRetentionPolicy:
    """Insert one valid active policy snapshot for the test tenant."""
    now = datetime.now(UTC)
    policy = CandidateRetentionPolicy(
        tenant_id=tenant_id,
        policy_version=1,
        status=CandidateRetentionPolicyStatus.ACTIVE,
        unsuccessful_applicant_days=365,
        withdrawn_applicant_days=365,
        talent_pool_days=365,
        hired_recruiting_copy_days=90,
        created_by_subject="retention-policy-admin",
        activated_by_subject="retention-policy-admin",
        activated_at=now,
    )
    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        session.add(policy)
    return policy


def _review_payload(
    policy_id: UUID,
    *,
    disposition: str = "retain",
    reason_code: str = "not_yet_due",
    next_review_at: str | None = None,
) -> dict[str, Any]:
    """Build strict review input with no free-form personal notes."""
    return {
        "policy_id": str(policy_id),
        "purpose": "unsuccessful_applicant",
        "disposition": disposition,
        "reason_code": reason_code,
        "checklist": {
            "active_matters_reviewed": True,
            "legal_holds_reviewed": True,
            "other_lawful_basis_reviewed": True,
            "employee_obligations_reviewed": True,
            "external_processors_reviewed": True,
            "backup_restore_safeguards_reviewed": True,
        },
        "next_review_at": next_review_at or (datetime.now(UTC) + timedelta(days=30)).isoformat(),
    }


@pytest.mark.asyncio
async def test_retention_review_create_replays_and_recommendation_does_not_erase(
    retention_api_app: FastAPI,
    database_engine: AsyncEngine,
    retention_tenant_id: UUID,
) -> None:
    """Replay returns the stored evidence and does not erase or duplicate audit."""
    transport = ASGITransport(app=retention_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        policy = await _create_active_policy(
            database_engine,
            tenant_id=retention_tenant_id,
        )
        _set_context(
            retention_api_app,
            tenant_id=retention_tenant_id,
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
        )
        url = f"/api/v1/candidates/{candidate['id']}/retention-reviews"
        payload = _review_payload(
            policy.id,
            disposition="recommend_manual_erasure",
            reason_code="review_complete",
        )
        payload["next_review_at"] = None
        headers = {"Idempotency-Key": "retention-review-replay-test"}

        first = await client.post(url, json=payload, headers=headers)
        replay = await client.post(url, json=payload, headers=headers)

    assert first.status_code == replay.status_code == 201
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert replay.headers["Cache-Control"] == "private, no-store"
    assert first.json() == replay.json()
    assert first.json()["disposition"] == "recommend_manual_erasure"
    assert first.json()["review_number"] == 1
    assert "Private Review Candidate" not in first.text
    assert "private.review.candidate@example.test" not in first.text

    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with session_factory() as session:
        stored_candidate = await session.get(Candidate, UUID(candidate["id"]))
        reviews = list(await session.scalars(select(CandidateRetentionReview)))
        audit_events = list(
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action == "candidate.retention_review_recorded")
            )
        )
    assert stored_candidate is not None
    assert stored_candidate.privacy_status is CandidatePrivacyStatus.ACTIVE
    assert len(reviews) == 1
    assert len(audit_events) == 1


@pytest.mark.asyncio
async def test_retention_review_history_uses_stable_private_cursor_pages(
    retention_api_app: FastAPI,
    database_engine: AsyncEngine,
    retention_tenant_id: UUID,
) -> None:
    """Return review evidence newest-first without exposing candidate PII."""
    transport = ASGITransport(app=retention_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        policy = await _create_active_policy(
            database_engine,
            tenant_id=retention_tenant_id,
        )
        _set_context(
            retention_api_app,
            tenant_id=retention_tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        url = f"/api/v1/candidates/{candidate['id']}/retention-reviews"
        for index in range(2):
            created = await client.post(
                url,
                json=_review_payload(
                    policy.id,
                    next_review_at=(datetime.now(UTC) + timedelta(days=30 + index)).isoformat(),
                ),
                headers={"Idempotency-Key": f"retention-review-page-{index}"},
            )
            assert created.status_code == 201

        first_page = await client.get(url, params={"limit": 1})
        second_page = await client.get(
            url,
            params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
        )

    assert first_page.status_code == second_page.status_code == 200
    assert first_page.headers["Cache-Control"] == "private, no-store"
    assert second_page.headers["Cache-Control"] == "private, no-store"
    assert first_page.json()["items"][0]["review_number"] == 2
    assert second_page.json()["items"][0]["review_number"] == 1
    assert second_page.json()["next_cursor"] is None
    assert "email" not in first_page.json()["items"][0]
    assert "full_name" not in first_page.json()["items"][0]


@pytest.mark.asyncio
async def test_retention_review_authorization_isolation_and_validation_are_private(
    retention_api_app: FastAPI,
    database_engine: AsyncEngine,
    retention_tenant_id: UUID,
) -> None:
    """Enforce reviewer roles, hide other tenants, and reject unsafe input."""
    other_tenant_id = uuid4()
    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=other_tenant_id,
                name="Other Retention Review Tenant",
                slug=f"other-retention-{other_tenant_id.hex[:12]}",
            )
        )

    transport = ASGITransport(app=retention_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        policy = await _create_active_policy(
            database_engine,
            tenant_id=retention_tenant_id,
        )
        url = f"/api/v1/candidates/{candidate['id']}/retention-reviews"

        _set_context(
            retention_api_app,
            tenant_id=retention_tenant_id,
            roles=frozenset({Role.RECRUITER}),
        )
        forbidden_response = await client.get(url)

        _set_context(
            retention_api_app,
            tenant_id=other_tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        hidden_response = await client.post(
            url,
            json=_review_payload(policy.id),
            headers={"Idempotency-Key": str(uuid4())},
        )

        _set_context(
            retention_api_app,
            tenant_id=retention_tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        invalid_cursor = await client.get(url, params={"cursor": "not-a-cursor"})
        invalid_schema = await client.post(
            url,
            json={**_review_payload(policy.id), "private_notes": "must-not-be-echoed"},
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert forbidden_response.status_code == 403
    assert hidden_response.status_code == 404
    assert invalid_cursor.status_code == 422
    assert invalid_schema.status_code == 422
    assert all(
        response.headers["Cache-Control"] == "private, no-store"
        for response in (
            forbidden_response,
            hidden_response,
            invalid_cursor,
            invalid_schema,
        )
    )
    assert "must-not-be-echoed" not in invalid_schema.text


@pytest.mark.asyncio
async def test_retention_review_audit_contains_only_controlled_review_values(
    retention_api_app: FastAPI,
    database_engine: AsyncEngine,
    retention_tenant_id: UUID,
) -> None:
    """Ensure review audit records omit candidate identity and contact data."""
    transport = ASGITransport(app=retention_api_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        policy = await _create_active_policy(
            database_engine,
            tenant_id=retention_tenant_id,
        )
        _set_context(
            retention_api_app,
            tenant_id=retention_tenant_id,
            roles=frozenset({Role.PEOPLE_OPERATIONS}),
        )
        response = await client.post(
            f"/api/v1/candidates/{candidate['id']}/retention-reviews",
            json=_review_payload(policy.id),
            headers={"Idempotency-Key": str(uuid4())},
        )

    assert response.status_code == 201
    session_factory = async_sessionmaker(database_engine, expire_on_commit=False)
    async with session_factory() as session:
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.action == "candidate.retention_review_recorded")
        )
    assert event is not None
    assert event.details == {
        "review_number": 1,
        "policy_version": 1,
        "purpose": "unsuccessful_applicant",
        "disposition": "retain",
        "reason_code": "not_yet_due",
    }
    assert "Private Review Candidate" not in str(event.details)
    assert "private.review.candidate@example.test" not in str(event.details)
