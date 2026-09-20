"""Infisical-backed storage for tenant-owned HRIS credentials."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Protocol, cast
from uuid import uuid4

from infisical_sdk import (  # type: ignore[import-untyped]
    InfisicalError,
    InfisicalSDKClient,
)
from pydantic import SecretStr

from app.services.hris_credentials import (
    HrisCredentials,
    HrisCredentialVaultError,
)

_HRIS_CREDENTIAL_PATH = "/hris-credentials/"
_HRIS_REFERENCE_PREFIX = "tap-hris-"  # noqa: S105
_HRIS_REFERENCE_PATTERN = re.compile(r"^tap-hris-[a-f0-9]{32}$")
_CREDENTIAL_FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CREDENTIAL_PAYLOAD_BYTES = 64 * 1024


class _SecretsClient(Protocol):
    """Minimal Infisical secret API surface used by this adapter."""

    def create_secret_by_name(self, **kwargs: object) -> object:
        """Create a secret by name."""

    def get_secret_by_name(self, **kwargs: object) -> object:
        """Read a secret by name."""

    def delete_secret_by_name(self, **kwargs: object) -> object:
        """Delete a secret by name."""


class _InfisicalClient(Protocol):
    """Minimal authenticated Infisical SDK client."""

    secrets: _SecretsClient


def _status_code(error: BaseException) -> int | None:
    """Read an HTTP status without inspecting provider error text."""
    direct_status = getattr(error, "status_code", None)
    if isinstance(direct_status, int):
        return direct_status

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None


def _is_retryable(error: BaseException) -> bool:
    """Classify transient secret-vault failures conservatively."""
    if isinstance(error, (OSError, TimeoutError)):
        return True

    status_code = _status_code(error)
    if status_code is None:
        return True

    return status_code == 408 or status_code == 429 or status_code >= 500


def _is_not_found(error: BaseException) -> bool:
    """Recognize an explicit Infisical not-found response."""
    return _status_code(error) == 404


class InfisicalHrisCredentialVault:
    """
    Store HRIS credentials using opaque random secret references.

    PostgreSQL stores the reference only. Provider, tenant, employee, and
    credential values never appear in secret names, audit events, logs, or
    outbox payloads.
    """

    def __init__(
        self,
        *,
        project_id: str,
        environment_slug: str,
        client: _InfisicalClient,
    ) -> None:
        if not project_id.strip():
            raise ValueError("Infisical project ID must not be empty.")

        if not environment_slug.strip():
            raise ValueError("Infisical environment must not be empty.")

        self._project_id = project_id
        self._environment_slug = environment_slug
        self._client = client

    @classmethod
    async def from_universal_auth(
        cls,
        *,
        project_id: str,
        environment_slug: str,
        client_id: str,
        client_secret: str,
        host: str = "https://app.infisical.com",
    ) -> InfisicalHrisCredentialVault:
        """Create an authenticated Infisical client outside the event loop."""

        def build_client() -> _InfisicalClient:
            client = InfisicalSDKClient(host=host)
            client.auth.universal_auth.login(
                client_id=client_id,
                client_secret=client_secret,
            )
            return cast(_InfisicalClient, client)

        client = await asyncio.to_thread(build_client)

        return cls(
            project_id=project_id,
            environment_slug=environment_slug,
            client=client,
        )

    @staticmethod
    def _new_reference() -> str:
        """Create an application-owned opaque secret reference."""
        return f"{_HRIS_REFERENCE_PREFIX}{uuid4().hex}"

    @staticmethod
    def _validate_reference(credential_reference: str) -> str:
        """Permit reads and deletes only in the HRIS secret namespace."""
        if not _HRIS_REFERENCE_PATTERN.fullmatch(credential_reference):
            raise HrisCredentialVaultError(
                "hris_credential_reference_invalid",
                retryable=False,
            )

        return credential_reference

    @staticmethod
    def _serialize_credentials(credentials: HrisCredentials) -> str:
        """Serialize credentials only for the Infisical API call."""
        payload: dict[str, str] = {}

        for name, value in credentials.values.items():
            if not _CREDENTIAL_FIELD_PATTERN.fullmatch(name):
                raise HrisCredentialVaultError(
                    "hris_credential_field_invalid",
                    retryable=False,
                )

            payload[name] = value.get_secret_value()

        serialized = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )

        if len(serialized.encode("utf-8")) > _MAX_CREDENTIAL_PAYLOAD_BYTES:
            raise HrisCredentialVaultError(
                "hris_credential_payload_too_large",
                retryable=False,
            )

        return serialized

    @staticmethod
    def _deserialize_credentials(raw_secret: object) -> HrisCredentials:
        """Validate one Infisical secret before returning it in memory."""
        if not isinstance(raw_secret, str):
            raise HrisCredentialVaultError(
                "hris_credential_payload_invalid",
                retryable=False,
            )

        try:
            payload: object = json.loads(raw_secret)
        except json.JSONDecodeError as error:
            raise HrisCredentialVaultError(
                "hris_credential_payload_invalid",
                retryable=False,
            ) from error

        if not isinstance(payload, dict):
            raise HrisCredentialVaultError(
                "hris_credential_payload_invalid",
                retryable=False,
            )

        values: dict[str, SecretStr] = {}

        for name, value in payload.items():
            if (
                not isinstance(name, str)
                or not _CREDENTIAL_FIELD_PATTERN.fullmatch(name)
                or not isinstance(value, str)
                or not value
            ):
                raise HrisCredentialVaultError(
                    "hris_credential_payload_invalid",
                    retryable=False,
                )

            values[name] = SecretStr(value)

        try:
            return HrisCredentials(values=values)
        except ValueError as error:
            raise HrisCredentialVaultError(
                "hris_credential_payload_invalid",
                retryable=False,
            ) from error

    async def store_hris_credentials(
        self,
        *,
        provider: str,
        tenant_id: str,
        credentials: HrisCredentials,
    ) -> str:
        """Store one credential set and return an opaque random reference."""
        # These are intentionally never placed in secret names or metadata.
        del provider, tenant_id

        credential_reference = self._new_reference()
        payload = self._serialize_credentials(credentials)

        try:
            await asyncio.to_thread(
                self._client.secrets.create_secret_by_name,
                secret_name=credential_reference,
                secret_value=payload,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_HRIS_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            raise HrisCredentialVaultError(
                "hris_credential_store_failed",
                retryable=_is_retryable(error),
            ) from error

        return credential_reference

    async def resolve_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> HrisCredentials:
        """Resolve one application-owned secret only into worker memory."""
        secret_name = self._validate_reference(credential_reference)

        try:
            secret = await asyncio.to_thread(
                self._client.secrets.get_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_HRIS_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                raise HrisCredentialVaultError(
                    "hris_credential_not_found",
                    retryable=False,
                ) from error

            raise HrisCredentialVaultError(
                "hris_credential_resolution_failed",
                retryable=_is_retryable(error),
            ) from error

        return self._deserialize_credentials(getattr(secret, "secretValue", None))

    async def delete_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> None:
        """Delete one HRIS credential secret during compensation or revocation."""
        secret_name = self._validate_reference(credential_reference)

        try:
            await asyncio.to_thread(
                self._client.secrets.delete_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_HRIS_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                return

            raise HrisCredentialVaultError(
                "hris_credential_delete_failed",
                retryable=_is_retryable(error),
            ) from error
