"""HTTP integration tests for private offer workflow endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import get_db_session, get_tenant_context
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.application import Application
from app.db.models.approval import ApprovalPolicy, ApprovalPolicyStep
from app.db.models.candidate import Candidate
from app.db.models.identity import Tenant, User
from app.db.models.requisition import Requisition
from app.domains.candidates.enums import ApplicationStatus, CandidateConsentStatus
from app.domains.requisitions.enums import RequisitionStatus
from app.main import create_app


def _test_settings() -> Settings:
    """Build isolated settings without using local environment values."""
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
            request_id="offer-api-test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Build request-scoped sessions against the isolated test database."""
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
    """Set the verified identity used by the next API request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id,
        subject=subject,
        roles=roles,
    )


def _headers() -> dict[str, str]:
    """Generate a unique idempotency key for one write operation."""
    return {"Idempotency-Key": str(uuid4())}


def _offer_payload() -> dict[str, object]:
    """Return valid private compensation data."""
    return {
        "currency": "KES",
        "base_salary": "250000.00",
        "bonus_amount": "20000.00",
        "pay_period": "monthly",
        "equity_summary": "Eligible for the employee share plan.",
        "proposed_start_date": (
            datetime.now(UTC).date() + timedelta(days=30)
        ).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
    }


async def _create_tenant(
    engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create a tenant required by foreign-key constrained fixtures."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        session.add(
            Tenant(
                id=tenant_id,
                name=f"Offer API Tenant {tenant_id.hex[:12]}",
                slug=f"offer-api-{tenant_id.hex[:12]}",
            )
        )


async def _seed_offer_application(
    engine: AsyncEngine,
    *,
    tenant_id: UUID,
    approver_subjects: tuple[str, ...] = (
        "approver-one-subject",
        "approver-two-subject",
    ),
) -> Application:
    """Create an offer-stage application and its default approval policy."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory.begin() as session:
        recruiter = User(
            tenant_id=tenant_id,
            external_subject="recruiter-subject",
            email=f"recruiter-{tenant_id.hex[:12]}@example.test",
            display_name="Recruiter",
        )
        approvers = [
            User(
                tenant_id=tenant_id,
                external_subject=subject,
                email=f"{subject}-{tenant_id.hex[:8]}@example.test",
                display_name=subject.replace("-", " ").title(),
            )
            for subject in approver_subjects
        ]
        session.add_all([recruiter, *approvers])

        candidate = Candidate(
            tenant_id=tenant_id,
            full_name="Ada Lovelace",
            email=f"ada-{tenant_id.hex[:12]}@example.test",
            normalized_email=f"ada-{tenant_id.hex[:12]}@example.test",
            source="employee_referral",
            source_metadata={},
            consent_status=CandidateConsentStatus.GRANTED,
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
            status=ApplicationStatus.OFFER,
            created_by_subject="recruiter-subject",
        )
        session.add(application)
        await session.flush()

        policy = ApprovalPolicy(
            tenant_id=tenant_id,
            name="Default offer approval policy",
            is_default=True,
            is_active=True,
        )
        session.add(policy)
        await session.flush()

        session.add_all(
            [
                ApprovalPolicyStep(
                    approval_policy_id=policy.id,
                    position=position,
                    approver_user_id=user.id,
                )
                for position, user in enumerate(approvers, start=1)
            ]
        )

        return application


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Create the default API caller's tenant."""
    value = uuid4()
    await _create_tenant(database_engine, value)
    return value


@pytest_asyncio.fixture(name="api_app")
async def api_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> AsyncIterator[FastAPI]:
    """Create the API with test database and verified-caller overrides."""
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
async def test_creates_draft_offer_idempotently_with_private_response(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Create once and replay the exact private response for the same key."""
    application = await _seed_offer_application(
        database_engine,
        tenant_id=tenant_id,
    )
    headers = _headers()
    payload = _offer_payload()

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=payload,
            headers=headers,
        )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert first.json() == replay.json()
    assert first.json()["status"] == "draft"
    assert first.json()["currency"] == "KES"
    assert first.headers["Idempotent-Replayed"] == "false"
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_submits_approves_sends_and_accepts_offer(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Exercise the complete private offer workflow through HTTP."""
    application = await _seed_offer_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=_offer_payload(),
            headers=_headers(),
        )
        offer_id = created.json()["id"]

        submitted = await client.post(
            f"/api/v1/offers/{offer_id}/approval-submissions",
            json={"expected_offer_version": 1},
            headers=_headers(),
        )
        approval_id = submitted.json()["id"]

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-one-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        first_approval = await client.post(
            f"/api/v1/offer-approvals/{approval_id}/decisions",
            json={
                "expected_offer_version": 2,
                "decision": "approved",
            },
            headers=_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-two-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        final_approval = await client.post(
            f"/api/v1/offer-approvals/{approval_id}/decisions",
            json={
                "expected_offer_version": 2,
                "decision": "approved",
            },
            headers=_headers(),
        )

        _set_context(api_app, tenant_id=tenant_id)
        signature_request = await client.post(
            f"/api/v1/offers/{offer_id}/signature-requests",
            json={
                "expected_offer_version": 3,
                "provider": "example-sign",
                "document_reference": "offer-document-reference",
            },
            headers=_headers(),
        )
        signature_request_id = signature_request.json()["id"]

        sent_signature = await client.post(
            f"/api/v1/offer-signature-requests/{signature_request_id}/send",
            json={
                "expected_version": signature_request.json()["version"],
                "provider_envelope_reference": "provider-envelope-reference",
            },
            headers=_headers(),
        )
        signed = await client.post(
            f"/api/v1/offer-signature-requests/{signature_request_id}/sign",
            json={"expected_version": sent_signature.json()["version"]},
            headers=_headers(),
        )
        sent = await client.post(
            f"/api/v1/offers/{offer_id}/send",
            json={"expected_offer_version": 3},
            headers=_headers(),
        )
        accepted = await client.post(
            f"/api/v1/offers/{offer_id}/accept",
            json={"expected_offer_version": 4},
            headers=_headers(),
        )

    assert created.status_code == 201
    assert submitted.status_code == 201
    assert first_approval.status_code == 200
    assert final_approval.status_code == 200
    assert final_approval.json()["status"] == "approved"
    assert sent.status_code == 200
    assert sent.json()["status"] == "sent"
    assert signature_request.status_code == 201
    assert sent_signature.status_code == 200
    assert signed.status_code == 200
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["version"] == 5
    assert accepted.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_replays_approval_decision_and_rejects_out_of_order_approver(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Only the current approver can decide; replay is safe."""
    application = await _seed_offer_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=_offer_payload(),
            headers=_headers(),
        )
        offer_id = created.json()["id"]

        submitted = await client.post(
            f"/api/v1/offers/{offer_id}/approval-submissions",
            json={"expected_offer_version": 1},
            headers=_headers(),
        )
        approval_id = submitted.json()["id"]

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-two-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        out_of_order = await client.post(
            f"/api/v1/offer-approvals/{approval_id}/decisions",
            json={
                "expected_offer_version": 2,
                "decision": "approved",
            },
            headers=_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            subject="approver-one-subject",
            roles=frozenset({Role.HIRING_MANAGER}),
        )
        headers = _headers()
        payload = {
            "expected_offer_version": 2,
            "decision": "approved",
        }
        first = await client.post(
            f"/api/v1/offer-approvals/{approval_id}/decisions",
            json=payload,
            headers=headers,
        )
        replay = await client.post(
            f"/api/v1/offer-approvals/{approval_id}/decisions",
            json=payload,
            headers=headers,
        )

    assert out_of_order.status_code == 403
    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json() == replay.json()
    assert replay.headers["Idempotent-Replayed"] == "true"


@pytest.mark.asyncio
async def test_rejects_stale_version_unknown_fields_and_unauthorized_role(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Enforce strict contracts, concurrency, and operational authorization."""
    application = await _seed_offer_application(
        database_engine,
        tenant_id=tenant_id,
    )

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        unknown_field = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json={**_offer_payload(), "unexpected_field": "must fail"},
            headers=_headers(),
        )

        _set_context(
            api_app,
            tenant_id=tenant_id,
            roles=frozenset({Role.INTERVIEWER}),
        )
        forbidden = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=_offer_payload(),
            headers=_headers(),
        )

        _set_context(api_app, tenant_id=tenant_id)
        created = await client.post(
            f"/api/v1/applications/{application.id}/offers",
            json=_offer_payload(),
            headers=_headers(),
        )
        offer_id = created.json()["id"]

        stale = await client.post(
            f"/api/v1/offers/{offer_id}/approval-submissions",
            json={"expected_offer_version": 2},
            headers=_headers(),
        )

    assert unknown_field.status_code == 422
    assert forbidden.status_code == 403
    assert stale.status_code == 409


@pytest.mark.asyncio
async def test_hides_offer_from_another_tenant(
    api_app: FastAPI,
    database_engine: AsyncEngine,
    tenant_id: UUID,
) -> None:
    """Do not reveal tenant-owned offer existence outside its tenant."""
    owner_tenant_id = uuid4()
    await _create_tenant(database_engine, owner_tenant_id)
    owner_application = await _seed_offer_application(
        database_engine,
        tenant_id=owner_tenant_id,
    )

    _set_context(api_app, tenant_id=owner_tenant_id)

    async with AsyncClient(
        transport=ASGITransport(app=api_app),
        base_url="http://testserver",
    ) as client:
        created = await client.post(
            f"/api/v1/applications/{owner_application.id}/offers",
            json=_offer_payload(),
            headers=_headers(),
        )
        offer_id = created.json()["id"]

        _set_context(api_app, tenant_id=tenant_id)
        response = await client.post(
            f"/api/v1/offers/{offer_id}/cancel",
            json={"expected_offer_version": 1},
            headers=_headers(),
        )

    assert created.status_code == 201
    assert response.status_code == 404
