"""Tests for the hardened Infisical calendar credential vault."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
from infisical_sdk import InfisicalError  # type: ignore[import-untyped]
from pydantic import SecretStr

from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    CalendarCredentialVaultError,
    ResolvedCalendarCredentials,
)

PROJECT_ID = "test-project-id"
ENVIRONMENT = "dev"


class _InfisicalApiError(InfisicalError):
    """Infisical test error with an explicit non-sensitive HTTP status."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class _FakeBaseSecret:
    """Minimal stand-in for an Infisical secret response."""

    # These names mirror the third-party Infisical SDK response fields.
    # pylint: disable=invalid-name
    secretKey: str
    secretValue: str


@dataclass
class _FakeSecrets:
    """Records calls and permits deterministic provider failures."""

    stored: dict[str, _FakeBaseSecret] = field(default_factory=dict)
    created: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[dict[str, Any]] = field(default_factory=list)
    operation_thread_ids: list[int] = field(default_factory=list)

    create_error: Exception | None = None
    get_error: Exception | None = None
    delete_error: Exception | None = None

    def create_secret_by_name(self, **kwargs: object) -> _FakeBaseSecret:
        """Record a secret creation request."""
        self.operation_thread_ids.append(threading.get_ident())

        if self.create_error is not None:
            raise self.create_error

        payload = dict(kwargs)
        self.created.append(cast(dict[str, Any], payload))

        secret_name = cast(str, kwargs["secret_name"])
        secret_value = cast(str, kwargs["secret_value"])
        secret = _FakeBaseSecret(
            secretKey=secret_name,
            secretValue=secret_value,
        )
        self.stored[secret_name] = secret
        return secret

    def get_secret_by_name(self, **kwargs: object) -> _FakeBaseSecret:
        """Return a stored secret or raise the configured error."""
        self.operation_thread_ids.append(threading.get_ident())

        if self.get_error is not None:
            raise self.get_error

        secret_name = cast(str, kwargs["secret_name"])
        secret = self.stored.get(secret_name)
        if secret is None:
            raise _InfisicalApiError(
                "missing",
                status_code=404,
            )

        return secret

    def delete_secret_by_name(self, **kwargs: object) -> _FakeBaseSecret:
        """Delete a stored secret or raise the configured error."""
        self.operation_thread_ids.append(threading.get_ident())

        if self.delete_error is not None:
            raise self.delete_error

        payload = dict(kwargs)
        self.deleted.append(cast(dict[str, Any], payload))

        secret_name = cast(str, kwargs["secret_name"])
        secret = self.stored.pop(
            secret_name,
            _FakeBaseSecret(secretKey=secret_name, secretValue=""),
        )
        return secret


@dataclass
class _FakeInfisicalClient:
    """Minimal authenticated Infisical client substitute."""

    secrets: _FakeSecrets = field(default_factory=_FakeSecrets)


@pytest.fixture(name="fake_infisical_client")
def fake_infisical_client_fixture() -> _FakeInfisicalClient:
    """Provide an isolated fake client."""
    return _FakeInfisicalClient()


@pytest.fixture(name="vault")
def vault_fixture(
    fake_infisical_client: _FakeInfisicalClient,
) -> InfisicalCredentialVault:
    """Provide a vault using the fake client."""
    return InfisicalCredentialVault(
        project_id=PROJECT_ID,
        environment_slug=ENVIRONMENT,
        client=fake_infisical_client,
    )


def _sample_credentials() -> ResolvedCalendarCredentials:
    """Return representative OAuth credentials."""
    return ResolvedCalendarCredentials(
        values={
            "access_token": SecretStr("test-access-token"),
            "refresh_token": SecretStr("test-refresh-token"),
        },
    )


async def test_store_generates_opaque_unique_references(
    vault: InfisicalCredentialVault,
) -> None:
    """Secret references must not disclose provider, tenant, or owner IDs."""
    first = await vault.store(
        provider="google",
        tenant_id="tenant-private-value",
        owner_user_id="owner-private-value",
        credentials=_sample_credentials(),
    )
    second = await vault.store(
        provider="google",
        tenant_id="tenant-private-value",
        owner_user_id="owner-private-value",
        credentials=_sample_credentials(),
    )

    assert first != second
    assert first.startswith("tap-calendar-")
    assert "google" not in first
    assert "tenant-private-value" not in first
    assert "owner-private-value" not in first


async def test_store_serializes_credentials_without_extra_metadata(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Only credential values belong in the secret payload."""
    await vault.store(
        provider="google",
        tenant_id="tenant-id",
        owner_user_id="owner-id",
        credentials=_sample_credentials(),
    )

    created = fake_infisical_client.secrets.created[0]

    assert created["project_id"] == PROJECT_ID
    assert created["environment_slug"] == ENVIRONMENT
    assert created["secret_path"] == "/calendar-credentials/"  # noqa: S105
    assert json.loads(cast(str, created["secret_value"])) == {
        "access_token": "test-access-token",
        "refresh_token": "test-refresh-token",
    }


async def test_store_rejects_invalid_credential_field_name(
    vault: InfisicalCredentialVault,
) -> None:
    """Do not write unrecognised or unsafe credential field names."""
    credentials = ResolvedCalendarCredentials(
        values={"refresh-token": SecretStr("secret")}
    )

    with pytest.raises(CalendarCredentialVaultError) as exc_info:
        await vault.store(
            provider="google",
            tenant_id="tenant-id",
            owner_user_id="owner-id",
            credentials=credentials,
        )

    assert exc_info.value.code == "calendar_credential_field_invalid"
    assert exc_info.value.retryable is False


async def test_store_classifies_provider_outage_as_retryable(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Temporary Infisical failures must be safe to retry."""
    fake_infisical_client.secrets.create_error = _InfisicalApiError(
        "unavailable",
        status_code=503,
    )

    with pytest.raises(CalendarCredentialVaultError) as exc_info:
        await vault.store(
            provider="google",
            tenant_id="tenant-id",
            owner_user_id="owner-id",
            credentials=_sample_credentials(),
        )

    assert exc_info.value.code == "calendar_credential_store_failed"
    assert exc_info.value.retryable is True


async def test_resolve_returns_in_memory_credentials(
    vault: InfisicalCredentialVault,
) -> None:
    """Resolve persisted credentials without changing their values."""
    reference = await vault.store(
        provider="google",
        tenant_id="tenant-id",
        owner_user_id="owner-id",
        credentials=_sample_credentials(),
    )

    resolved = await vault.resolve(credential_reference=reference)

    assert resolved.required("access_token").get_secret_value() == (
        "test-access-token"
    )
    assert resolved.required("refresh_token").get_secret_value() == (
        "test-refresh-token"
    )


async def test_resolve_rejects_invalid_reference(
    vault: InfisicalCredentialVault,
) -> None:
    """Workers may resolve only application-owned credential references."""
    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(
            credential_reference="other-application-secret"
        )

    assert exc_info.value.code == "calendar_credential_reference_invalid"
    assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [
        "not-json",
        "[]",
        '{"refresh-token":"value"}',
        '{"refresh_token":123}',
    ],
)
async def test_resolve_rejects_malformed_secret_payloads(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
    payload: str,
) -> None:
    """Malformed vault content must never reach calendar providers."""
    reference = "tap-calendar-" + "a" * 32
    fake_infisical_client.secrets.stored[reference] = _FakeBaseSecret(
        secretKey=reference,
        secretValue=payload,
    )

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(credential_reference=reference)

    assert exc_info.value.code == "calendar_credential_payload_invalid"
    assert exc_info.value.retryable is False


async def test_resolve_classifies_not_found_as_non_retryable(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """A deleted credential must not cause endless worker retries."""
    fake_infisical_client.secrets.get_error = _InfisicalApiError(
        "missing",
        status_code=404,
    )

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(
            credential_reference="tap-calendar-" + "b" * 32
        )

    assert exc_info.value.code == "calendar_credential_not_found"
    assert exc_info.value.retryable is False


async def test_resolve_classifies_provider_outage_as_retryable(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Temporary provider failures must permit the outbox worker to retry."""
    fake_infisical_client.secrets.get_error = _InfisicalApiError(
        "unavailable",
        status_code=503,
    )

    with pytest.raises(CalendarCredentialResolutionError) as exc_info:
        await vault.resolve(
            credential_reference="tap-calendar-" + "c" * 32
        )

    assert exc_info.value.code == "calendar_credential_resolution_failed"
    assert exc_info.value.retryable is True


async def test_delete_is_idempotent_only_for_not_found(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """A confirmed missing secret is safe to treat as already deleted."""
    fake_infisical_client.secrets.delete_error = _InfisicalApiError(
        "missing",
        status_code=404,
    )

    await vault.delete(
        credential_reference="tap-calendar-" + "d" * 32
    )


async def test_delete_propagates_provider_outage(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """Do not silently lose a failed cleanup operation."""
    fake_infisical_client.secrets.delete_error = _InfisicalApiError(
        "unavailable",
        status_code=503,
    )

    with pytest.raises(CalendarCredentialVaultError) as exc_info:
        await vault.delete(
            credential_reference="tap-calendar-" + "e" * 32
        )

    assert exc_info.value.code == "calendar_credential_delete_failed"
    assert exc_info.value.retryable is True


async def test_sdk_operations_run_outside_the_event_loop(
    vault: InfisicalCredentialVault,
    fake_infisical_client: _FakeInfisicalClient,
) -> None:
    """The synchronous SDK must not block the async application event loop."""
    event_loop_thread = threading.get_ident()

    reference = await vault.store(
        provider="google",
        tenant_id="tenant-id",
        owner_user_id="owner-id",
        credentials=_sample_credentials(),
    )
    await vault.resolve(credential_reference=reference)
    await vault.delete(credential_reference=reference)

    assert fake_infisical_client.secrets.operation_thread_ids
    assert all(
        thread_id != event_loop_thread
        for thread_id in fake_infisical_client.secrets.operation_thread_ids
    )
