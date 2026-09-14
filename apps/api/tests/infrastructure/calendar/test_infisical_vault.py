"""Tests for the Infisical calendar credential vault."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest
from infisical_sdk import InfisicalError  # type: ignore[import-untyped]
from pydantic import SecretStr

from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    ResolvedCalendarCredentials,
)

# ---------------------------------------------------------------------------
# Fake Infisical secret type
# ---------------------------------------------------------------------------


@dataclass
class _FakeBaseSecret:
    """Minimal stand-in for ``infisical_sdk.api_types.BaseSecret``."""

    # These names mirror the third-party Infisical SDK response fields.
    # pylint: disable=invalid-name

    secretKey: str
    secretValue: str
    id: str = "fake-id"
    _id: str = "fake-id"
    workspace: str = "fake-workspace"
    environment: str = "dev"
    version: int = 1
    type: str = "shared"
    secretComment: str = ""
    createdAt: str = "2026-01-01T00:00:00Z"
    updatedAt: str = "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Fake Infisical secrets resource
# ---------------------------------------------------------------------------


@dataclass
class _FakeSecrets:
    """Records calls and returns canned responses for unit testing."""

    stored: dict[str, _FakeBaseSecret] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)

    # If set, get_secret_by_name raises this instead of returning.
    get_error: Exception | None = None

    # If set, delete_secret_by_name raises this instead of succeeding.
    delete_error: Exception | None = None

    def create_secret_by_name(self, **kwargs: Any) -> _FakeBaseSecret:
        """Record and store a newly created fake secret."""
        self.created.append(kwargs)
        secret = _FakeBaseSecret(
            secretKey=kwargs["secret_name"],
            secretValue=kwargs["secret_value"],
        )
        self.stored[kwargs["secret_name"]] = secret
        return secret

    def get_secret_by_name(self, **kwargs: Any) -> _FakeBaseSecret:
        """Return a stored fake secret or raise the configured error."""
        if self.get_error is not None:
            raise self.get_error

        name = kwargs["secret_name"]
        if name not in self.stored:
            raise InfisicalError(f"Secret not found: {name}")
        return self.stored[name]

    def delete_secret_by_name(self, **kwargs: Any) -> _FakeBaseSecret:
        """Record deletion and remove the fake secret from storage."""
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted.append(kwargs)
        name = kwargs["secret_name"]
        return self.stored.pop(name, _FakeBaseSecret(secretKey=name, secretValue=""))


# ---------------------------------------------------------------------------
# Fake Infisical client
# ---------------------------------------------------------------------------


@dataclass
class _FakeInfisicalClient:
    """Minimal stand-in for ``InfisicalSDKClient``."""

    secrets: _FakeSecrets = field(default_factory=_FakeSecrets)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_ID = "test-project-id"
ENVIRONMENT = "dev"


@pytest.fixture(name="fake_infisical_client")
def _fake_infisical_client_fixture() -> _FakeInfisicalClient:
    """Return a fake Infisical client for vault tests."""
    return _FakeInfisicalClient()


@pytest.fixture(name="vault")
def _vault_fixture(
    fake_infisical_client: _FakeInfisicalClient,
) -> InfisicalCredentialVault:
    """Return a vault configured with the fake Infisical client."""
    return InfisicalCredentialVault(
        project_id=PROJECT_ID,
        environment_slug=ENVIRONMENT,
        client=fake_infisical_client,
    )


def _sample_credentials() -> ResolvedCalendarCredentials:
    """Return deterministic credentials for vault tests."""
    return ResolvedCalendarCredentials(
        values={
            "access_token": SecretStr("at-test-123"),
            "refresh_token": SecretStr("rt-test-456"),
        },
    )


# ---------------------------------------------------------------------------
# store() tests
# ---------------------------------------------------------------------------


async def test_store_creates_secret(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Store credentials by creating one Infisical secret."""
    reference = await vault.store(
        provider="google",
        tenant_id="tenant-abc",
        owner_user_id="user-xyz",
        credentials=_sample_credentials(),
    )

    assert len(fake_infisical_client.secrets.created) == 1
    assert reference.startswith("calendar-creds-google-tenant-abc-user-xyz-")


async def test_store_generates_unique_references(
    vault: InfisicalCredentialVault,
) -> None:
    """Generate a unique opaque reference for each credential set."""
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
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Serialize credential values as a JSON secret payload."""
    await vault.store(
        provider="microsoft",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    create_call = fake_infisical_client.secrets.created[0]
    payload = json.loads(create_call["secret_value"])

    assert payload == {
        "access_token": "at-test-123",
        "refresh_token": "rt-test-456",
    }


async def test_secret_name_uses_opaque_ids(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Include provider, tenant, and owner identifiers in secret names."""
    await vault.store(
        provider="google",
        tenant_id="tid-111",
        owner_user_id="uid-222",
        credentials=_sample_credentials(),
    )

    secret_name = fake_infisical_client.secrets.created[0]["secret_name"]
    assert "google" in secret_name
    assert "tid-111" in secret_name
    assert "uid-222" in secret_name


# ---------------------------------------------------------------------------
# delete() tests
# ---------------------------------------------------------------------------


async def test_delete_destroys_secret(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Delete the secret associated with a credential reference."""
    reference = await vault.store(
        provider="google",
        tenant_id="t1",
        owner_user_id="u1",
        credentials=_sample_credentials(),
    )

    await vault.delete(credential_reference=reference)

    assert len(fake_infisical_client.secrets.deleted) == 1
    assert fake_infisical_client.secrets.deleted[0]["secret_name"] == reference


async def test_delete_ignores_not_found(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Treat a missing secret as an idempotent delete."""
    fake_infisical_client.secrets.delete_error = InfisicalError("Secret not found")

    # Should not raise.
    await vault.delete(credential_reference="nonexistent-secret")


# ---------------------------------------------------------------------------
# resolve() tests
# ---------------------------------------------------------------------------


async def test_resolve_returns_credentials(
    vault: InfisicalCredentialVault,
) -> None:
    """Resolve stored JSON into secret credential values."""
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
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Classify a missing Infisical secret as non-retryable."""
    fake_infisical_client.secrets.get_error = InfisicalError("Secret not found")

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(credential_reference="gone-secret")

    assert exc_info.value.code == "calendar_credential_not_found"
    assert exc_info.value.retryable is False


async def test_resolve_transient_error_raises_retryable(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Classify a transient Infisical failure as retryable."""
    fake_infisical_client.secrets.get_error = InfisicalError("service unavailable")

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(credential_reference="temp-fail-secret")

    assert exc_info.value.code == "calendar_credential_resolution_failed"
    assert exc_info.value.retryable is True
