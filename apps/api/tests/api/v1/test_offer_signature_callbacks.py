"""HTTP integration tests for public verified offer-signature callbacks."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_db_session,
    get_offer_signature_callback_verifiers,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.offer_signature import OfferSignatureRequest
from app.db.models.offer_signature_callback import (
    OfferSignatureCallbackReceipt,
)
from app.domains.signatures.enums import OfferSignatureStatus
from app.infrastructure.signatures.local_callback_verifier import (
    LocalOfferSignatureCallbackVerifier,
)
from app.main import create_app
from app.services.offer_signatures import (
    CreateOfferSignatureRequestCommand,
    create_offer_signature_request,
    send_offer_signature_request,
)
from tests.services.test_offer_signatures import _seed_approved_offer

_CALLBACK_SECRET = (
    "offer-signature-callback-test-secret"  # noqa: S105 -- test-only value
)
_CALLBACK_PATH = "/api/v1/integrations/offer-signatures/local/callbacks"


def _settings() -> Settings:
    """Build isolated settings with a deliberately small callback body limit."""
    return Settings(
        app_env="test",
        app_name="talent-acquisition-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=None,
        redis_url="redis://localhost:6379/0",
        allowed_origins=[],
        offer_signature_callback_max_body_bytes=1_024,
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Provide request-scoped test database sessions."""

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


def _verifier_dependency() -> dict[str, LocalOfferSignatureCallbackVerifier]:
    """Provide the trusted local callback verifier without application startup."""
    return {
        "local": LocalOfferSignatureCallbackVerifier(
            signing_secret=SecretStr(_CALLBACK_SECRET),
        )
    }


def _body(
    *,
    event_id: str = "provider-event-1",
    envelope_reference: str,
    event_type: str = "signed",
    occurred_at: datetime | None = None,
) -> bytes:
    """Build a strict local-provider callback event body."""
    return json.dumps(
        {
            "event_id": event_id,
            "envelope_reference": envelope_reference,
            "event_type": event_type,
            "occurred_at": (
                occurred_at or datetime.now(UTC)
            ).astimezone(UTC).isoformat().replace("+00:00", "Z"),
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _headers(
    body: bytes,
    *,
    timestamp: datetime | None = None,
    signature: str | None = None,
) -> dict[str, str]:
    """Sign the exact callback bytes using the local provider contract."""
    signed_at = timestamp or datetime.now(UTC)
    unix_timestamp = str(int(signed_at.astimezone(UTC).timestamp()))

    expected_signature = hmac.new(
        _CALLBACK_SECRET.encode("utf-8"),
        unix_timestamp.encode("ascii") + b"." + body,
        hashlib.sha256,
    ).hexdigest()

    return {
        "Content-Type": "application/json",
        "X-TAP-Timestamp": unix_timestamp,
        "X-TAP-Signature": signature or f"v1={expected_signature}",
    }


def _context(tenant_id: UUID) -> TenantContext:
    """Build trusted internal setup context for signature request creation."""
    return TenantContext(
        tenant_id=tenant_id,
        subject="recruiter-subject",
        roles=frozenset({Role.RECRUITER}),
        request_id="offer-signature-callback-api-test-request-id",
    )


async def _seed_sent_signature_request(
    engine: AsyncEngine,
) -> OfferSignatureRequest:
    """Create a sent local-provider signature request and opaque envelope."""
    tenant_id = uuid4()
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        offer = await _seed_approved_offer(
            session,
            tenant_id=tenant_id,
        )
        context = _context(tenant_id)

        signature_request = await create_offer_signature_request(
            session,
            context=context,
            offer_id=offer.id,
            expected_offer_version=offer.version,
            command=CreateOfferSignatureRequestCommand(
                provider="local",
                document_reference="private-document-reference",
            ),
        )

        return await send_offer_signature_request(
            session,
            context=context,
            signature_request_id=signature_request.id,
            expected_version=signature_request.version,
            provider_envelope_reference=f"envelope-{signature_request.id}",
        )


async def _load_signature_state(
    engine: AsyncEngine,
    *,
    signature_request_id: UUID,
) -> tuple[OfferSignatureRequest, int]:
    """Load signature state and callback receipt count after an HTTP request."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        signature_request = await session.get(
            OfferSignatureRequest,
            signature_request_id,
        )
        assert signature_request is not None

        receipt_rows = await session.execute(
            select(OfferSignatureCallbackReceipt).where(
                OfferSignatureCallbackReceipt.offer_signature_request_id
                == signature_request_id
            )
        )
        receipt_count = len(receipt_rows.scalars().all())

        return signature_request, receipt_count


@pytest_asyncio.fixture(name="callback_app")
async def callback_app_fixture(
    database_engine: AsyncEngine,
) -> AsyncIterator[FastAPI]:
    """Create the callback API with trusted verifier and database overrides."""
    application = create_app(_settings())

    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.dependency_overrides[
        get_offer_signature_callback_verifiers
    ] = _verifier_dependency

    yield application

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_accepts_valid_signed_callback_and_hides_all_details(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """A valid signed provider callback changes lifecycle state privately."""
    signature_request = await _seed_sent_signature_request(database_engine)
    body = _body(
        envelope_reference=signature_request.provider_envelope_reference or "",
    )

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=_headers(body),
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert response.status_code == 202
    assert response.headers["Cache-Control"] == "no-store"
    assert response.content == b""
    assert "provider-event-1" not in response.text
    assert "envelope" not in response.text.lower()

    assert signature_state.status is OfferSignatureStatus.SIGNED
    assert receipt_count == 1


@pytest.mark.asyncio
async def test_replays_valid_callback_without_duplicate_receipt(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Provider retries receive the same generic acknowledgement safely."""
    signature_request = await _seed_sent_signature_request(database_engine)
    body = _body(
        envelope_reference=signature_request.provider_envelope_reference or "",
    )
    headers = _headers(body)

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        first = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=headers,
        )
        replay = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=headers,
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert first.content == b""
    assert replay.content == b""
    assert signature_state.status is OfferSignatureStatus.SIGNED
    assert receipt_count == 1


@pytest.mark.asyncio
async def test_acknowledges_invalid_hmac_without_mutating_state(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Invalid signatures receive no useful oracle and do not alter records."""
    signature_request = await _seed_sent_signature_request(database_engine)
    body = _body(
        envelope_reference=signature_request.provider_envelope_reference or "",
    )

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=_headers(body, signature="v1=invalid-signature"),
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert response.status_code == 202
    assert response.headers["Cache-Control"] == "no-store"
    assert response.content == b""
    assert "invalid-signature" not in response.text

    assert signature_state.status is OfferSignatureStatus.SENT
    assert receipt_count == 0


@pytest.mark.asyncio
async def test_acknowledges_stale_timestamp_without_mutating_state(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Callbacks outside the replay window cannot affect signature lifecycle."""
    signature_request = await _seed_sent_signature_request(database_engine)
    body = _body(
        envelope_reference=signature_request.provider_envelope_reference or "",
    )

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=_headers(
                body,
                timestamp=datetime.now(UTC) - timedelta(minutes=6),
            ),
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert response.status_code == 202
    assert response.headers["Cache-Control"] == "no-store"
    assert response.content == b""
    assert signature_state.status is OfferSignatureStatus.SENT
    assert receipt_count == 0


@pytest.mark.asyncio
async def test_rejects_oversized_callback_body_before_verification(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Large callback bodies are rejected before parsing or signature handling."""
    signature_request = await _seed_sent_signature_request(database_engine)
    oversized_body = b"x" * 1_025

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            _CALLBACK_PATH,
            content=oversized_body,
            headers=_headers(oversized_body),
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert response.status_code == 413
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["detail"] == "Callback body is too large."
    assert signature_state.status is OfferSignatureStatus.SENT
    assert receipt_count == 0


@pytest.mark.asyncio
async def test_hides_unknown_callback_provider(
    callback_app: FastAPI,
) -> None:
    """Unconfigured providers do not reveal callback runtime configuration."""
    body = _body(envelope_reference="unknown-envelope")

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/integrations/offer-signatures/unknown/callbacks",
            content=body,
            headers=_headers(body),
        )

    assert response.status_code == 404
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["detail"] == "Not found."
    assert "unknown" not in response.text.lower()


@pytest.mark.asyncio
async def test_callback_responses_never_reflect_signer_pii_or_raw_body(
    callback_app: FastAPI,
    database_engine: AsyncEngine,
) -> None:
    """Provider input remains private even when the callback is rejected."""
    signature_request = await _seed_sent_signature_request(database_engine)
    body = json.dumps(
        {
            "event_id": "private-event",
            "envelope_reference": (
                signature_request.provider_envelope_reference or ""
            ),
            "event_type": "signed",
            "occurred_at": datetime.now(UTC).isoformat(),
            "signer_email": "private@example.test",
        },
        separators=(",", ":"),
    ).encode("utf-8")

    async with AsyncClient(
        transport=ASGITransport(app=callback_app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            _CALLBACK_PATH,
            content=body,
            headers=_headers(body),
        )

    signature_state, receipt_count = await _load_signature_state(
        database_engine,
        signature_request_id=signature_request.id,
    )

    assert response.status_code == 202
    assert response.headers["Cache-Control"] == "no-store"
    assert response.content == b""
    assert "private@example.test" not in response.text
    assert "signer_email" not in response.text
    assert signature_state.status is OfferSignatureStatus.SENT
    assert receipt_count == 0
