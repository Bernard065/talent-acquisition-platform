"""HTTP integration tests for candidate and application endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.audit import AuditEvent
from app.db.models.candidate_talent_pool_consent import (
    CandidateTalentPoolConsentEvent,
)
from app.db.models.identity import Tenant
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import CandidateConsentStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without relying on a local environment file."""
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
    """Return a verified-caller dependency for one test identity."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=roles,
            request_id="test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped session dependency for ASGI endpoint tests."""
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
    """Return a unique idempotency key for one write request."""
    return {"Idempotency-Key": str(uuid4())}


def _set_context(
    application: FastAPI,
    *,
    tenant_id: UUID,
    roles: frozenset[Role],
) -> None:
    """Replace the verified caller for a subsequent test request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        roles,
    )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the tenant required by candidate and requisition foreign keys."""
    value = uuid4()
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=value,
                name="Candidate API Test Tenant",
                slug=f"candidate-api-{value.hex[:12]}",
            )
        )

    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the application with only auth and database access overridden."""
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


async def _create_candidate(
    client: AsyncClient,
    *,
    email: str = "ada@acme.io",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create one candidate through the public API."""
    response = await client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Ada Lovelace",
            "email": email,
            "source": "employee_referral",
            "source_metadata": {"campaign": "engineering-q3"},
        },
        headers=headers or _idempotency_headers(),
    )

    assert response.status_code == 201
    return response.json()


async def _create_requisition(
    database_engine: AsyncEngine,
    *,
    tenant_id: UUID,
    status: RequisitionStatus,
) -> Requisition:
    """Seed a requisition for application endpoint preconditions."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        requisition = Requisition(
            tenant_id=tenant_id,
            title="Senior Backend Engineer",
            headcount=1,
            status=status,
            created_by_subject="recruiter-subject",
        )
        session.add(requisition)
        await session.flush()

        return requisition


@pytest.mark.asyncio
async def test_replays_candidate_creation_for_same_idempotency_key(
    api_app: FastAPI,
) -> None:
    """Replay candidate creation when the idempotency key is reused."""
    transport = ASGITransport(app=api_app)
    headers = _idempotency_headers()
    payload = {
        "full_name": "Ada Lovelace",
        "email": "ada@acme.io",
        "source": "employee_referral",
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=headers,
        )
        second = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert second.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_duplicate_candidate_with_a_new_idempotency_key(
    api_app: FastAPI,
) -> None:
    """Reject a duplicate candidate submitted with a new idempotency key."""
    transport = ASGITransport(app=api_app)
    payload = {
        "full_name": "Ada Lovelace",
        "email": "Ada.Lovelace@Acme.IO",
        "source": "employee_referral",
    }

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post(
            "/api/v1/candidates",
            json=payload,
            headers=_idempotency_headers(),
        )
        second = await client.post(
            "/api/v1/candidates",
            json={
                **payload,
                    "email": "ada.lovelace@acme.io",
            },
            headers=_idempotency_headers(),
        )

    assert first.status_code == 201
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_hides_candidate_from_another_tenant(
    api_app: FastAPI,
) -> None:
    """Hide a candidate when the caller belongs to another tenant."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)

        _set_context(
            api_app,
            tenant_id=uuid4(),
            roles=frozenset({Role.RECRUITER}),
        )
        response = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate or application not found."


@pytest.mark.asyncio
async def test_candidate_get_response_is_private_and_not_cached(
    api_app: FastAPI,
) -> None:
    """Return private cache headers when retrieving a candidate."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        response = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == candidate["id"]
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_rejects_application_when_requisition_is_not_open(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Reject applications for requisitions that are not open."""
    transport = ASGITransport(app=api_app)
    requisition = await _create_requisition(
        database_engine,
        tenant_id=tenant_id,
        status=RequisitionStatus.DRAFT,
    )

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        response = await client.post(
            "/api/v1/applications",
            json={
                "candidate_id": candidate["id"],
                "requisition_id": str(requisition.id),
            },
            headers=_idempotency_headers(),
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_creates_application_for_open_requisition_and_marks_private(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create an application and return private cache headers."""
    transport = ASGITransport(app=api_app)
    requisition = await _create_requisition(
        database_engine,
        tenant_id=tenant_id,
        status=RequisitionStatus.OPEN,
    )

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        created = await client.post(
            "/api/v1/applications",
            json={
                "candidate_id": candidate["id"],
                "requisition_id": str(requisition.id),
            },
            headers=_idempotency_headers(),
        )
        fetched = await client.get(f"/api/v1/applications/{created.json()['id']}")

    assert created.status_code == 201
    assert created.json()["status"] == "applied"
    assert created.headers["Cache-Control"] == "private, no-store"
    assert fetched.status_code == 200
    assert fetched.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_withdraws_candidate_consent_idempotently_without_pii(
    api_app: FastAPI,
) -> None:
    transport = ASGITransport(app=api_app)
    headers = _idempotency_headers()

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        first = await client.post(
            f"/api/v1/candidates/{candidate['id']}/consent/withdraw",
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/candidates/{candidate['id']}/consent/withdraw",
            headers=headers,
        )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert first.json()["consent_status"] == "withdrawn"
    assert first.json()["privacy_status"] == "active"
    assert "email" not in first.json()
    assert "full_name" not in first.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert first.json()["candidate_id"] == candidate["id"]


@pytest.mark.asyncio
async def test_erasure_anonymizes_candidate_and_hides_profile(
    api_app: FastAPI,
    tenant_id: UUID,
) -> None:
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        _set_context(
            api_app,
            tenant_id=tenant_id,
            roles=frozenset({Role.TENANT_ADMIN}),
        )
        erasure = await client.post(
            f"/api/v1/candidates/{candidate['id']}/erasure",
            headers=_idempotency_headers(),
        )
        hidden = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert erasure.status_code == 202
    assert erasure.json()["privacy_status"] == "erased"
    assert erasure.json()["consent_status"] == "withdrawn"
    assert "email" not in erasure.json()
    assert "full_name" not in erasure.json()
    assert erasure.headers["Cache-Control"] == "private, no-store"
    assert hidden.status_code == 404
    assert hidden.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_recruiter_cannot_request_candidate_erasure(
    api_app: FastAPI,
) -> None:
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        response = await client.post(
            f"/api/v1/candidates/{candidate['id']}/erasure",
            headers=_idempotency_headers(),
        )

    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_talent_pool_consent_grant_replays_without_exposing_candidate_pii(
    api_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Grant one consent event once and return the stored response on replay."""
    transport = ASGITransport(app=api_app)
    headers = _idempotency_headers()
    payload = {"notice_version": "privacy-notice-2026-01", "capture_method": "signed_form"}

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        url = f"/api/v1/candidates/{candidate['id']}/talent-pool-consent/grant"
        first = await client.post(url, json=payload, headers=headers)
        replay = await client.post(url, json=payload, headers=headers)
        mismatched_reuse = await client.post(
            url,
            json={**payload, "notice_version": "notice-v2"},
            headers=headers,
        )
        profile = await client.get(f"/api/v1/candidates/{candidate['id']}")

    assert first.status_code == replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["event_type"] == "granted"
    assert first.json()["event_version"] == 1
    assert first.json()["capture_method"] == "signed_form"
    assert first.json()["notice_version"] == payload["notice_version"]
    assert "email" not in first.json()
    assert "full_name" not in first.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert mismatched_reuse.status_code == 409
    assert mismatched_reuse.headers["Cache-Control"] == "private, no-store"
    assert profile.status_code == 200
    assert profile.json()["consent_status"] == CandidateConsentStatus.UNKNOWN.value

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        event_count = await session.scalar(
            select(func.count())
            .select_from(CandidateTalentPoolConsentEvent)
            .where(
                CandidateTalentPoolConsentEvent.candidate_id
                == UUID(candidate["id"])
            )
        )
    assert event_count == 1


@pytest.mark.asyncio
async def test_talent_pool_consent_renewal_and_withdrawal_append_audited_versions(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Renew and withdraw through the API while preserving append-only evidence."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        base = f"/api/v1/candidates/{candidate['id']}/talent-pool-consent"
        grant = await client.post(
            f"{base}/grant",
            json={"notice_version": "notice-v1", "capture_method": "email_confirmation"},
            headers=_idempotency_headers(),
        )
        renewal = await client.post(
            f"{base}/renew",
            json={"notice_version": "notice-v2", "capture_method": "signed_form"},
            headers=_idempotency_headers(),
        )
        withdrawal = await client.post(
            f"{base}/withdraw",
            json={"capture_method": "recruiter_recorded"},
            headers=_idempotency_headers(),
        )

    assert grant.status_code == renewal.status_code == 201
    assert withdrawal.status_code == 200
    assert [
        grant.json()["event_version"],
        renewal.json()["event_version"],
        withdrawal.json()["event_version"],
    ] == [1, 2, 3]
    assert [
        grant.json()["event_type"],
        renewal.json()["event_type"],
        withdrawal.json()["event_type"],
    ] == ["granted", "renewed", "withdrawn"]
    assert all(
        response.headers["Cache-Control"] == "private, no-store"
        for response in (grant, renewal, withdrawal)
    )

    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        events = list(
            (
                await session.scalars(
                    select(CandidateTalentPoolConsentEvent)
                    .where(CandidateTalentPoolConsentEvent.candidate_id == UUID(candidate["id"]))
                    .order_by(CandidateTalentPoolConsentEvent.event_version)
                )
            ).all()
        )
        audit_count = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.action.like("candidate.talent_pool_consent_%"),
            )
        )

    assert [event.event_version for event in events] == [1, 2, 3]
    assert audit_count == 3


@pytest.mark.asyncio
async def test_talent_pool_consent_hides_cross_tenant_candidate_and_denies_analyst(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Consent routes enforce tenant isolation and the consent-specific role set."""
    transport = ASGITransport(app=api_app)
    other_tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )
    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=other_tenant_id,
                name="Other Candidate API Tenant",
                slug=f"other-candidate-api-{other_tenant_id.hex[:12]}",
            )
        )

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        url = f"/api/v1/candidates/{candidate['id']}/talent-pool-consent/grant"
        payload = {"notice_version": "notice-v1", "capture_method": "signed_form"}

        _set_context(api_app, tenant_id=tenant_id, roles=frozenset({Role.ANALYST}))
        forbidden_response = await client.post(
            url,
            json=payload,
            headers=_idempotency_headers(),
        )

        _set_context(
            api_app,
            tenant_id=other_tenant_id,
            roles=frozenset({Role.RECRUITER}),
        )
        hidden_response = await client.post(
            url,
            json=payload,
            headers=_idempotency_headers(),
        )

    assert forbidden_response.status_code == 403
    assert forbidden_response.headers["Cache-Control"] == "private, no-store"
    assert hidden_response.status_code == 404
    assert hidden_response.json()["detail"] == "Candidate or application not found."
    assert hidden_response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_talent_pool_consent_rejects_invalid_state_and_strict_fields_privately(
    api_app: FastAPI,
) -> None:
    """Map state and schema failures to safe, non-cacheable responses."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        candidate = await _create_candidate(client)
        grant_url = f"/api/v1/candidates/{candidate['id']}/talent-pool-consent/grant"
        grant = await client.post(
            grant_url,
            json={"notice_version": "notice-v1", "capture_method": "signed_form"},
            headers=_idempotency_headers(),
        )
        invalid_state = await client.post(
            grant_url,
            json={"notice_version": "notice-v1", "capture_method": "signed_form"},
            headers=_idempotency_headers(),
        )
        invalid_schema = await client.post(
            f"/api/v1/candidates/{candidate['id']}/talent-pool-consent/renew",
            json={
                "notice_version": "notice-v2",
                "capture_method": "candidate_portal",
                "unexpected": "must-not-be-echoed",
            },
            headers=_idempotency_headers(),
        )

    assert grant.status_code == 201
    assert invalid_state.status_code == 409
    assert invalid_schema.status_code == 422
    assert invalid_state.headers["Cache-Control"] == "private, no-store"
    assert invalid_schema.headers["Cache-Control"] == "private, no-store"
    assert "must-not-be-echoed" not in invalid_schema.text


@pytest.mark.asyncio
async def test_talent_pool_search_exposes_only_currently_consented_candidates(
    api_app: FastAPI,
) -> None:
    """Return current consent evidence and exclude candidates after withdrawal."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        active_candidate = await _create_candidate(
            client,
            email="active-talent@example.test",
        )
        withdrawn_candidate = await _create_candidate(
            client,
            email="withdrawn-talent@example.test",
        )
        for candidate in (active_candidate, withdrawn_candidate):
            grant = await client.post(
                f"/api/v1/candidates/{candidate['id']}/talent-pool-consent/grant",
                json={
                    "notice_version": "notice-v1",
                    "capture_method": "signed_form",
                },
                headers=_idempotency_headers(),
            )
            assert grant.status_code == 201

        withdrawal = await client.post(
            f"/api/v1/candidates/{withdrawn_candidate['id']}"
            "/talent-pool-consent/withdraw",
            json={"capture_method": "email_confirmation"},
            headers=_idempotency_headers(),
        )
        response = await client.get("/api/v1/candidates/talent-pool")

    assert withdrawal.status_code == 200
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert [item["candidate_id"] for item in response.json()["items"]] == [
        active_candidate["id"]
    ]
    consented_profile = response.json()["items"][0]
    assert consented_profile["consent_notice_version"] == "notice-v1"
    assert consented_profile["consent_capture_method"] == "signed_form"
    assert "source_metadata" not in consented_profile
    assert response.json()["next_cursor"] is None


@pytest.mark.asyncio
async def test_talent_pool_search_authorization_cursor_and_validation_are_private(
    api_app: FastAPI,
) -> None:
    """Use private no-store errors for forbidden and invalid search requests."""
    transport = ASGITransport(app=api_app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        _set_context(
            api_app,
            tenant_id=uuid4(),
            roles=frozenset({Role.INTERVIEWER}),
        )
        forbidden_response = await client.get("/api/v1/candidates/talent-pool")

        _set_context(
            api_app,
            tenant_id=uuid4(),
            roles=frozenset({Role.RECRUITER}),
        )
        invalid_cursor = await client.get(
            "/api/v1/candidates/talent-pool?cursor=invalid"
        )
        invalid_limit = await client.get(
            "/api/v1/candidates/talent-pool?limit=101"
        )

    assert forbidden_response.status_code == 403
    assert invalid_cursor.status_code == 422
    assert invalid_limit.status_code == 422
    assert all(
        response.headers["Cache-Control"] == "private, no-store"
        for response in (forbidden_response, invalid_cursor, invalid_limit)
    )
