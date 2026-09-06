"""HTTP integration tests for candidate document workflow endpoints."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.dependencies import (
    get_db_session,
    get_object_storage,
    get_tenant_context,
)
from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.db.models.identity import Tenant
from app.main import create_app
from app.services.object_storage import (
    ObjectStorageError,
    PresignedUpload,
    StoredObjectMetadata,
)


class FakeObjectStorage:
    """Offline object-storage substitute for HTTP integration tests."""

    def __init__(self) -> None:
        self.upload_authorization_count = 0
        self.metadata_calls = 0
        self.metadata_error: ObjectStorageError | None = None
        self.metadata = StoredObjectMetadata(
            content_type="application/pdf",
            byte_size=512_000,
            checksum_sha256="a" * 64,
        )

    async def create_presigned_upload(
        self,
        *,
        object_key: str,
        content_type: str,
        checksum_sha256: str,
        expires_in: timedelta,
    ) -> PresignedUpload:
        """Return a new URL each time; signed URLs must not be replayed."""
        del object_key
        self.upload_authorization_count += 1

        return PresignedUpload(
            url=(
                "https://storage.example.test/signed-upload/"
                f"{self.upload_authorization_count}"
            ),
            required_headers={
                "Content-Type": content_type,
                "x-amz-checksum-sha256": checksum_sha256,
            },
            expires_at=datetime.now(UTC) + expires_in,
        )

    async def get_object_metadata(
        self,
        *,
        object_key: str,
    ) -> StoredObjectMetadata:
        """Return configured metadata or simulate storage unavailability."""
        del object_key
        self.metadata_calls += 1

        if self.metadata_error is not None:
            raise self.metadata_error

        return self.metadata

    async def delete_object(self, *, object_key: str) -> None:
        """Implement the storage contract; deletion is outside this test scope."""
        del object_key


def _test_settings() -> Settings:
    """Build isolated application settings without reading a local .env file."""
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
) -> Callable[[], Awaitable[TenantContext]]:
    """Return one verified recruiter context for a test tenant."""

    async def override() -> TenantContext:
        return TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-subject",
            roles=frozenset({Role.RECRUITER}),
            request_id="test-request-id",
        )

    return override


def _session_dependency(
    engine: AsyncEngine,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Return a request-scoped session dependency bound to the test database."""
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
    """Create one idempotency key for an externally initiated mutation."""
    return {"Idempotency-Key": str(uuid4())}


def _set_context(application: FastAPI, tenant_id: UUID) -> None:
    """Replace the verified caller for a subsequent request."""
    application.dependency_overrides[get_tenant_context] = _context_dependency(
        tenant_id
    )


@pytest_asyncio.fixture(name="tenant_id")
async def tenant_id_fixture(database_engine: AsyncEngine) -> UUID:
    """Persist the tenant used by the default verified caller."""
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
                name="Document API Test Tenant",
                slug=f"document-api-{value.hex[:12]}",
            )
        )

    return value


@pytest_asyncio.fixture(name="storage")
async def storage_fixture() -> FakeObjectStorage:
    """Provide one controllable object-storage fake per test."""
    return FakeObjectStorage()


@pytest_asyncio.fixture(name="document_app")
async def document_app_fixture(
    database_engine: AsyncEngine,
    tenant_id: UUID,
    storage: FakeObjectStorage,
) -> AsyncIterator[FastAPI]:
    """Create an API app with identity, database, and storage overridden."""
    application = create_app(_test_settings())
    application.dependency_overrides[get_db_session] = _session_dependency(
        database_engine
    )
    application.dependency_overrides[get_object_storage] = lambda: storage
    _set_context(application, tenant_id)

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


async def _create_candidate(client: AsyncClient) -> dict[str, Any]:
    """Create a candidate required before creating a document."""
    response = await client.post(
        "/api/v1/candidates",
        json={
            "full_name": "Ada Lovelace",
            "email": f"ada-{uuid4().hex[:12]}@example.com",
            "source": "employee_referral",
        },
        headers=_idempotency_headers(),
    )

    assert response.status_code == 201
    return response.json()


async def _create_document(
    client: AsyncClient,
    *,
    candidate_id: str,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create one document upload intent through the public API."""
    response = await client.post(
        "/api/v1/candidate-documents",
        json={
            "candidate_id": candidate_id,
            "original_filename": "resume.pdf",
            "declared_content_type": "application/pdf",
            "expected_byte_size": 512_000,
            "checksum_sha256": "a" * 64,
        },
        headers=headers or _idempotency_headers(),
    )

    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_replays_document_creation_for_same_idempotency_key(
    document_app: FastAPI,
) -> None:
    """Replay document creation without creating a second document record."""
    transport = ASGITransport(app=document_app)
    headers = _idempotency_headers()

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        payload = {
            "candidate_id": candidate["id"],
            "original_filename": "resume.pdf",
            "declared_content_type": "application/pdf",
            "expected_byte_size": 512_000,
            "checksum_sha256": "a" * 64,
        }

        first = await client.post(
            "/api/v1/candidate-documents",
            json=payload,
            headers=headers,
        )
        second = await client.post(
            "/api/v1/candidate-documents",
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
async def test_hides_document_from_another_tenant(
    document_app: FastAPI,
) -> None:
    """Return not-found rather than exposing cross-tenant document existence."""
    transport = ASGITransport(app=document_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        _set_context(document_app, uuid4())
        response = await client.get(
            f"/api/v1/candidate-documents/{document['id']}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate document not found."


@pytest.mark.asyncio
async def test_document_responses_are_private_and_not_cached(
    document_app: FastAPI,
) -> None:
    """Apply no-store caching rules to metadata and signed upload responses."""
    transport = ASGITransport(app=document_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        fetched = await client.get(
            f"/api/v1/candidate-documents/{document['id']}"
        )
        authorization = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/upload-authorizations",
            json={},
        )

    assert fetched.status_code == 200
    assert authorization.status_code == 200
    assert fetched.headers["Cache-Control"] == "private, no-store"
    assert authorization.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_upload_authorizations_are_fresh_and_not_idempotent_replays(
    document_app: FastAPI,
    storage: FakeObjectStorage,
) -> None:
    """Issue a fresh expiring URL on each authorization request."""
    transport = ASGITransport(app=document_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        first = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/upload-authorizations",
            json={},
        )
        second = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/upload-authorizations",
            json={},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["upload_url"] != second.json()["upload_url"]
    assert storage.upload_authorization_count == 2
    assert "Idempotent-Replayed" not in first.headers
    assert "Idempotent-Replayed" not in second.headers


@pytest.mark.asyncio
async def test_confirms_upload_idempotently(
    document_app: FastAPI,
    storage: FakeObjectStorage,
) -> None:
    """Verify storage metadata once and replay the persisted confirmation."""
    transport = ASGITransport(app=document_app)
    headers = _idempotency_headers()

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        first = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/confirm-upload",
            json={},
            headers=headers,
        )
        second = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/confirm-upload",
            json={},
            headers=headers,
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "uploaded"
    assert first.json() == second.json()
    assert first.headers["Idempotent-Replayed"] == "false"
    assert second.headers["Idempotent-Replayed"] == "true"
    assert first.headers["Cache-Control"] == "private, no-store"
    assert storage.metadata_calls == 1


@pytest.mark.asyncio
async def test_rejects_document_when_storage_metadata_does_not_match(
    document_app: FastAPI,
    storage: FakeObjectStorage,
) -> None:
    """Return rejected status when provider metadata differs from expectations."""
    storage.metadata = StoredObjectMetadata(
        content_type="application/pdf",
        byte_size=512_001,
        checksum_sha256="a" * 64,
    )
    transport = ASGITransport(app=document_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        response = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/confirm-upload",
            json={},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.asyncio
async def test_returns_retryable_error_when_object_storage_is_unavailable(
    document_app: FastAPI,
    storage: FakeObjectStorage,
) -> None:
    """Avoid exposing provider errors and keep storage outages retryable."""
    storage.metadata_error = ObjectStorageError("storage unavailable")
    transport = ASGITransport(app=document_app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        candidate = await _create_candidate(client)
        document = await _create_document(
            client,
            candidate_id=candidate["id"],
        )

        response = await client.post(
            f"/api/v1/candidate-documents/{document['id']}/confirm-upload",
            json={},
            headers=_idempotency_headers(),
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Document storage service is temporarily unavailable."
    )
    assert response.headers["Retry-After"] == "5"
