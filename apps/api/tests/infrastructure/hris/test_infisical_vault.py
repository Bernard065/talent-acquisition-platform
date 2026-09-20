"""Tests for the Infisical-backed HRIS credential vault."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from infisical_sdk import InfisicalError  # type: ignore[import-untyped]
from pydantic import SecretStr

from app.infrastructure.hris.infisical_vault import InfisicalHrisCredentialVault
from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVaultError,
)

_PROJECT_ID = "test-project"
_ENVIRONMENT = "dev"


class _InfisicalApiError(InfisicalError):
    """Fake Infisical HTTP error with a safe status code."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class _FakeSecret:
    """Minimal Infisical secret response."""

    secretKey: str  # pylint: disable=invalid-name
    secretValue: str  # pylint: disable=invalid-name


@dataclass
class _FakeSecrets:
    """In-memory fake for the required Infisical secret operations."""

    stored: dict[str, _FakeSecret] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)

    create_error: Exception | None = None
    get_error: Exception | None = None
    delete_error: Exception | None = None

    def create_secret_by_name(self, **kwargs: object) -> _FakeSecret:
        """Store one fake secret."""
        if self.create_error is not None:
            raise self.create_error

        payload = cast(dict[str, Any], dict(kwargs))
        self.created.append(payload)

        secret = _FakeSecret(
            secretKey=cast(str, kwargs["secret_name"]),
            secretValue=cast(str, kwargs["secret_value"]),
        )
        self.stored[secret.secretKey] = secret
        return secret

    def get_secret_by_name(self, **kwargs: object) -> _FakeSecret:
        """Return one fake secret."""
        if self.get_error is not None:
            raise self.get_error

        secret_name = cast(str, kwargs["secret_name"])
        secret = self.stored.get(secret_name)

        if secret is None:
            raise _InfisicalApiError("missing", status_code=404)

        return secret

    def delete_secret_by_name(self, **kwargs: object) -> _FakeSecret:
        """Delete one fake secret."""
        if self.delete_error is not None:
            raise self.delete_error

        payload = cast(dict[str, Any], dict(kwargs))
        self.deleted.append(payload)

        secret_name = cast(str, kwargs["secret_name"])
        return self.stored.pop(
            secret_name,
            _FakeSecret(secretKey=secret_name, secretValue=""),
        )


@dataclass
class _FakeInfisicalClient:
    """Minimal authenticated client substitute."""

    secrets: _FakeSecrets = field(default_factory=_FakeSecrets)


@pytest.fixture(name="fake_client")
def fake_client_fixture() -> _FakeInfisicalClient:
    """Provide an isolated fake client."""
    return _FakeInfisicalClient()


@pytest.fixture(name="vault")
def vault_fixture(
    fake_client: _FakeInfisicalClient,
) -> InfisicalHrisCredentialVault:
    """Provide the vault with no real Infisical calls."""
    return InfisicalHrisCredentialVault(
        project_id=_PROJECT_ID,
        environment_slug=_ENVIRONMENT,
        client=fake_client,
    )


def _credentials() -> HrisCredentials:
    """Build representative provider credentials."""
    return HrisCredentials(
        values={
            "api_token": SecretStr("test-api-token"),
            "client_secret": SecretStr("test-client-secret"),
        }
    )


async def test_store_uses_opaque_reference_and_private_secret_path(
    vault: InfisicalHrisCredentialVault,
    fake_client: _FakeInfisicalClient,
) -> None:
    """Do not expose provider or tenant identity in references or metadata."""
    reference = await vault.store_hris_credentials(
        provider="hibob",
        tenant_id="tenant-private-value",
        credentials=_credentials(),
    )

    created = fake_client.secrets.created[0]

    assert reference.startswith("tap-hris-")
    assert "hibob" not in reference
    assert "tenant-private-value" not in reference
    assert created["secret_path"] == "/hris-credentials/"  # noqa: S105
    assert json.loads(cast(str, created["secret_value"])) == {
        "api_token": "test-api-token",
        "client_secret": "test-client-secret",
    }


async def test_store_generates_unique_references(
    vault: InfisicalHrisCredentialVault,
) -> None:
    """Each credential set receives a new opaque identifier."""
    first = await vault.store_hris_credentials(
        provider="hibob",
        tenant_id="tenant-id",
        credentials=_credentials(),
    )
    second = await vault.store_hris_credentials(
        provider="hibob",
        tenant_id="tenant-id",
        credentials=_credentials(),
    )

    assert first != second


async def test_resolve_returns_credentials_only_in_memory(
    vault: InfisicalHrisCredentialVault,
) -> None:
    """Round-trip credentials without persisting their values elsewhere."""
    reference = await vault.store_hris_credentials(
        provider="hibob",
        tenant_id="tenant-id",
        credentials=_credentials(),
    )

    resolved = await vault.resolve_hris_credentials(
        credential_reference=reference
    )

    assert resolved.values["api_token"].get_secret_value() == "test-api-token"
    assert (
        resolved.values["client_secret"].get_secret_value()
        == "test-client-secret"
    )


async def test_resolve_rejects_foreign_reference(
    vault: InfisicalHrisCredentialVault,
) -> None:
    """Workers can resolve only application-owned HRIS references."""
    with pytest.raises(HrisCredentialVaultError) as error:
        await vault.resolve_hris_credentials(
            credential_reference="someone-elses-secret"
        )

    assert error.value.code == "hris_credential_reference_invalid"
    assert error.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"api-token":"value"}',
        '{"api_token":123}',
        '{"api_token":""}',
    ],
)
async def test_resolve_rejects_malformed_payload(
    vault: InfisicalHrisCredentialVault,
    fake_client: _FakeInfisicalClient,
    payload: str,
) -> None:
    """Malformed secrets must never reach an HRIS provider adapter."""
    reference = "tap-hris-" + "a" * 32
    fake_client.secrets.stored[reference] = _FakeSecret(
        secretKey=reference,
        secretValue=payload,
    )

    with pytest.raises(HrisCredentialVaultError) as error:
        await vault.resolve_hris_credentials(
            credential_reference=reference
        )

    assert error.value.code == "hris_credential_payload_invalid"
    assert error.value.retryable is False


async def test_classifies_not_found_as_terminal(
    vault: InfisicalHrisCredentialVault,
    fake_client: _FakeInfisicalClient,
) -> None:
    """A deleted secret must not cause endless outbox retries."""
    fake_client.secrets.get_error = _InfisicalApiError(
        "missing",
        status_code=404,
    )

    with pytest.raises(HrisCredentialVaultError) as error:
        await vault.resolve_hris_credentials(
            credential_reference="tap-hris-" + "b" * 32
        )

    assert error.value.code == "hris_credential_not_found"
    assert error.value.retryable is False


async def test_classifies_outages_as_retryable(
    vault: InfisicalHrisCredentialVault,
    fake_client: _FakeInfisicalClient,
) -> None:
    """Temporary vault failures remain safely retryable."""
    fake_client.secrets.create_error = _InfisicalApiError(
        "unavailable",
        status_code=503,
    )

    with pytest.raises(HrisCredentialVaultError) as error:
        await vault.store_hris_credentials(
            provider="hibob",
            tenant_id="tenant-id",
            credentials=_credentials(),
        )

    assert error.value.code == "hris_credential_store_failed"
    assert error.value.retryable is True


async def test_delete_is_idempotent_for_missing_secret(
    vault: InfisicalHrisCredentialVault,
) -> None:
    """Compensation remains safe if Infisical already removed the secret."""
    await vault.delete_hris_credentials(
        credential_reference="tap-hris-" + "c" * 32
    )
