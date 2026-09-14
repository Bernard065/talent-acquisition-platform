"""Tests for the Google Secret Manager calendar credential vault."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from google.api_core.exceptions import NotFound, ServiceUnavailable
from google.cloud.secretmanager_v1 import (
    AccessSecretVersionRequest,
    AccessSecretVersionResponse,
    AddSecretVersionRequest,
    CreateSecretRequest,
    DeleteSecretRequest,
    SecretPayload,
    SecretVersion,
)
from pydantic import SecretStr

from app.infrastructure.calendar.google_secret_manager_vault import (
    GoogleSecretManagerCredentialVault,
)
from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    ResolvedCalendarCredentials,
)

# ---------------------------------------------------------------------------
# Fake Google Secret Manager client
# ---------------------------------------------------------------------------


@dataclass
class _FakeSecretManagerClient:
    """Records calls and returns canned responses for unit testing."""

    created_secrets: list[CreateSecretRequest] = field(default_factory=list)
    added_versions: list[AddSecretVersionRequest] = field(default_factory=list)
    deleted_secrets: list[DeleteSecretRequest] = field(default_factory=list)
    accessed_versions: list[AccessSecretVersionRequest] = field(default_factory=list)

    # Pre-loaded payloads keyed by secret resource name.
    stored_payloads: dict[str, bytes] = field(default_factory=dict)

    # If set, access_secret_version raises this instead of returning.
    access_error: Exception | None = None

    # If set, delete_secret raises this instead of succeeding.
    delete_error: Exception | None = None

    def create_secret(self, *, request: Any) -> None:
        self.created_secrets.append(request)

    def add_secret_version(self, *, request: Any) -> SecretVersion:
        self.added_versions.append(request)
        # Store the payload so resolve() can retrieve it.
        self.stored_payloads[request.parent] = request.payload.data
        return SecretVersion(name=f"{request.parent}/versions/1")

    def delete_secret(self, *, request: Any) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted_secrets.append(request)
        self.stored_payloads.pop(request.name, None)

    def access_secret_version(self, *, request: Any) -> AccessSecretVersionResponse:
        self.accessed_versions.append(request)

        if self.access_error is not None:
            raise self.access_error

        # Derive secret name by stripping /versions/latest.
        secret_name = request.name.removesuffix("/versions/latest")
        payload = self.stored_payloads.get(secret_name)
        if payload is None:
            raise NotFound(f"Secret {secret_name} not found")

        return AccessSecretVersionResponse(
            name=f"{secret_name}/versions/1",
            payload=SecretPayload(data=payload),
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_ID = "test-project-123456"


@pytest.fixture
def fake_client() -> _FakeSecretManagerClient:
    return _FakeSecretManagerClient()


@pytest.fixture
def vault(fake_client: _FakeSecretManagerClient) -> GoogleSecretManagerCredentialVault:
    return GoogleSecretManagerCredentialVault(
        project_id=PROJECT_ID,
        client=fake_client,  # type: ignore[arg-type]
    )


def _sample_credentials() -> ResolvedCalendarCredentials:
    return ResolvedCalendarCredentials(
        values={
            "access_token": SecretStr("at-test-123"),
            "refresh_token": SecretStr("rt-test-456"),
        },
    )


# ---------------------------------------------------------------------------
# store() tests
# ---------------------------------------------------------------------------


async def test_store_creates_secret_and_version(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    reference = await vault.store(
        provider="google",
        tenant_id="tenant-abc",
        owner_user_id="user-xyz",
        credentials=_sample_credentials(),
    )

    assert len(fake_client.created_secrets) == 1
    assert len(fake_client.added_versions) == 1

    create_req = fake_client.created_secrets[0]
    assert create_req.parent == f"projects/{PROJECT_ID}"
    assert create_req.secret_id.startswith("calendar-creds-google-tenant-abc-user-xyz-")

    assert reference == f"projects/{PROJECT_ID}/secrets/{create_req.secret_id}"


async def test_store_generates_unique_references(
    vault: GoogleSecretManagerCredentialVault,
) -> None:
    ref1 = await vault.store(
        provider="google",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )
    ref2 = await vault.store(
        provider="google",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    assert ref1 != ref2


async def test_store_serializes_credentials_as_json(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    await vault.store(
        provider="microsoft",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    version_req = fake_client.added_versions[0]
    payload = json.loads(version_req.payload.data.decode("utf-8"))

    assert payload == {
        "access_token": "at-test-123",
        "refresh_token": "rt-test-456",
    }


async def test_secret_name_uses_opaque_ids(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    await vault.store(
        provider="google",
        tenant_id="tid-111",
        owner_user_id="uid-222",
        credentials=_sample_credentials(),
    )

    secret_id = fake_client.created_secrets[0].secret_id
    assert "google" in secret_id
    assert "tid-111" in secret_id
    assert "uid-222" in secret_id


# ---------------------------------------------------------------------------
# delete() tests
# ---------------------------------------------------------------------------


async def test_delete_destroys_secret(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    reference = await vault.store(
        provider="google",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    await vault.delete(credential_reference=reference)

    assert len(fake_client.deleted_secrets) == 1
    assert fake_client.deleted_secrets[0].name == reference


async def test_delete_ignores_not_found(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    fake_client.delete_error = NotFound("not found")

    # Should not raise.
    await vault.delete(
        credential_reference="projects/test-project-123456/secrets/nonexistent",
    )


# ---------------------------------------------------------------------------
# resolve() tests
# ---------------------------------------------------------------------------


async def test_resolve_returns_credentials(
    vault: GoogleSecretManagerCredentialVault,
) -> None:
    reference = await vault.store(
        provider="google",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    resolved = await vault.resolve(credential_reference=reference)

    assert resolved.required("access_token").get_secret_value() == "at-test-123"
    assert resolved.required("refresh_token").get_secret_value() == "rt-test-456"


async def test_resolve_not_found_raises_non_retryable(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    fake_client.access_error = NotFound("not found")

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(
            credential_reference="projects/test-project-123456/secrets/gone",
        )

    assert exc_info.value.code == "calendar_credential_not_found"
    assert exc_info.value.retryable is False


async def test_resolve_transient_error_raises_retryable(
    vault: GoogleSecretManagerCredentialVault,
    fake_client: _FakeSecretManagerClient,
) -> None:
    fake_client.access_error = ServiceUnavailable("backend unavailable")

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(
            credential_reference="projects/test-project-123456/secrets/temp-fail",
        )

    assert exc_info.value.code == "calendar_credential_resolution_failed"
    assert exc_info.value.retryable is True
