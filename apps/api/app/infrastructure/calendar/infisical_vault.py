"""Infisical implementation of the calendar credential vault."""

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

from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    CalendarCredentialVaultError,
    ResolvedCalendarCredentials,
)
from app.services.webhook_secrets import WebhookSigningSecretVaultError

_CREDENTIAL_PATH = "/calendar-credentials/"
_SECRET_PREFIX = "tap-calendar-"  # noqa: S105
_SECRET_REFERENCE_PATTERN = re.compile(r"^tap-calendar-[a-f0-9]{32}$")
_CREDENTIAL_FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_MAX_CREDENTIAL_PAYLOAD_BYTES = 64 * 1024
_WEBHOOK_SECRET_PATH = "/webhook-signing-secrets/"  # noqa: S105
_WEBHOOK_SECRET_PREFIX = "tap-webhook-"  # noqa: S105
_WEBHOOK_SECRET_REFERENCE_PATTERN = re.compile(r"^tap-webhook-[a-f0-9]{32}$")

class _SecretsClient(Protocol):
    """Minimal Infisical secrets API surface used by this adapter."""

    def create_secret_by_name(self, **kwargs: object) -> object:
        """Create one secret."""

    def get_secret_by_name(self, **kwargs: object) -> object:
        """Retrieve one secret."""

    def delete_secret_by_name(self, **kwargs: object) -> object:
        """Delete one secret."""

class _InfisicalClient(Protocol):
    """Minimal authenticated Infisical client surface."""

    secrets: _SecretsClient

def _status_code(error: BaseException) -> int | None:
    """Extract a provider status code without inspecting sensitive messages."""
    direct_status = getattr(error, "status_code", None)
    if isinstance(direct_status, int):
        return direct_status

    response = getattr(error, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status

    return None

def _is_retryable(error: BaseException) -> bool:
    """Classify provider failures conservatively for retry-safe workers."""
    if isinstance(error, (OSError, TimeoutError)):
        return True

    status_code = _status_code(error)
    if status_code is None:
        return True

    return status_code == 408 or status_code == 429 or status_code >= 500

def _is_not_found(error: BaseException) -> bool:
    """Recognize an explicit provider not-found response."""
    return _status_code(error) == 404

class InfisicalCredentialVault:
    """
    Store calendar OAuth credentials in Infisical.

    PostgreSQL retains only an opaque random secret reference. Credential
    values, tenant identifiers, user identifiers, and secret references are
    never logged, audited, or returned by this adapter.
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
    ) -> InfisicalCredentialVault:
        """
        Create an authenticated client outside the event loop.

        Universal Auth is suitable for local development and CI. Production
        should later use a platform-native machine identity where available.
        """
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
    def _credential_reference() -> str:
        """Generate a random reference with no tenant or user information."""
        return f"{_SECRET_PREFIX}{uuid4().hex}"

    @staticmethod
    def _validate_reference(credential_reference: str) -> str:
        """Reject references outside this application-owned secret namespace."""
        if not _SECRET_REFERENCE_PATTERN.fullmatch(credential_reference):
            raise CalendarCredentialResolutionError(
                "calendar_credential_reference_invalid",
                retryable=False,
            )

        return credential_reference

    @staticmethod
    def _serialize_credentials(
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        """Serialize validated credentials only for the Infisical API call."""
        payload: dict[str, str] = {}

        for name, value in credentials.values.items():
            if not _CREDENTIAL_FIELD_PATTERN.fullmatch(name):
                raise CalendarCredentialVaultError(
                    "calendar_credential_field_invalid",
                    retryable=False,
                )

            payload[name] = value.get_secret_value()

        serialized = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )

        if len(serialized.encode("utf-8")) > _MAX_CREDENTIAL_PAYLOAD_BYTES:
            raise CalendarCredentialVaultError(
                "calendar_credential_payload_too_large",
                retryable=False,
            )

        return serialized

    @staticmethod
    def _deserialize_credentials(raw_secret: object) -> ResolvedCalendarCredentials:
        """Validate a secret payload before returning in-memory credentials."""
        if not isinstance(raw_secret, str):
            raise CalendarCredentialResolutionError(
                "calendar_credential_payload_invalid",
                retryable=False,
            )

        try:
            payload: object = json.loads(raw_secret)
        except json.JSONDecodeError as error:
            raise CalendarCredentialResolutionError(
                "calendar_credential_payload_invalid",
                retryable=False,
            ) from error

        if not isinstance(payload, dict):
            raise CalendarCredentialResolutionError(
                "calendar_credential_payload_invalid",
                retryable=False,
            )

        values: dict[str, SecretStr] = {}
        for name, value in payload.items():
            if (
                not isinstance(name, str)
                or not _CREDENTIAL_FIELD_PATTERN.fullmatch(name)
                or not isinstance(value, str)
            ):
                raise CalendarCredentialResolutionError(
                    "calendar_credential_payload_invalid",
                    retryable=False,
                )

            values[name] = SecretStr(value)

        return ResolvedCalendarCredentials(values=values)

    async def store(
        self,
        *,
        provider: str,
        tenant_id: str,
        owner_user_id: str,
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        """
        Store one credential set and return an opaque random reference.

        Tenant and owner identifiers are accepted to satisfy the port, but are
        deliberately not used in secret names, values, metadata, or logs.
        """
        del provider, tenant_id, owner_user_id

        credential_reference = self._credential_reference()
        payload = self._serialize_credentials(credentials)

        try:
            await asyncio.to_thread(
                self._client.secrets.create_secret_by_name,
                secret_name=credential_reference,
                secret_value=payload,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            raise CalendarCredentialVaultError(
                "calendar_credential_store_failed",
                retryable=_is_retryable(error),
            ) from error

        return credential_reference

    async def resolve(
        self,
        *,
        credential_reference: str,
    ) -> ResolvedCalendarCredentials:
        """Resolve an application-owned credential reference into memory."""
        secret_name = self._validate_reference(credential_reference)

        try:
            secret = await asyncio.to_thread(
                self._client.secrets.get_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                raise CalendarCredentialResolutionError(
                    "calendar_credential_not_found",
                    retryable=False,
                ) from error

            raise CalendarCredentialResolutionError(
                "calendar_credential_resolution_failed",
                retryable=_is_retryable(error),
            ) from error

        return self._deserialize_credentials(getattr(secret, "secretValue", None))

    async def read_runtime_secret(self, *, secret_name: str) -> SecretStr:
        """Read one runtime configuration secret from Infisical.

        This is only for application-level configuration such as OAuth client
        credentials. Tenant-owned refresh tokens continue to use ``resolve``.
        """
        if not secret_name or len(secret_name) > 255:
            raise CalendarCredentialVaultError(
                "invalid_runtime_secret_reference",
                retryable=False,
            )

        try:
            response = await asyncio.to_thread(
                self._client.secrets.get_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path="/",  # noqa: S106
            )
        except Exception as error:
            raise CalendarCredentialVaultError(
                "calendar_credential_runtime_secret_read_failed",
                retryable=_is_retryable(error),
            ) from error

        secret_value = getattr(response, "secretValue", None)
        if not isinstance(secret_value, str) or not secret_value:
            raise CalendarCredentialVaultError(
                "invalid_runtime_secret_value",
                retryable=False,
            )

        return SecretStr(secret_value)

    @staticmethod
    def _webhook_secret_reference() -> str:
        """Generate an opaque reference with no tenant or endpoint identity."""
        return f"{_WEBHOOK_SECRET_PREFIX}{uuid4().hex}"

    @staticmethod
    def _validate_webhook_secret_reference(secret_reference: str) -> str:
        """Reject references outside the application-owned webhook namespace."""
        if not _WEBHOOK_SECRET_REFERENCE_PATTERN.fullmatch(secret_reference):
            raise WebhookSigningSecretVaultError(
                "webhook_secret_reference_invalid",
                retryable=False,
            )

        return secret_reference

    async def store_webhook_signing_secret(
        self,
        *,
        secret: SecretStr,
    ) -> str:
        """Store one webhook HMAC secret and return an opaque reference."""
        secret_value = secret.get_secret_value()
        if not secret_value:
            raise WebhookSigningSecretVaultError(
                "webhook_secret_invalid",
                retryable=False,
            )

        secret_reference = self._webhook_secret_reference()

        try:
            await asyncio.to_thread(
                self._client.secrets.create_secret_by_name,
                secret_name=secret_reference,
                secret_value=secret_value,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_WEBHOOK_SECRET_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            raise WebhookSigningSecretVaultError(
                "webhook_secret_store_failed",
                retryable=_is_retryable(error),
            ) from error

        return secret_reference

    async def resolve_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> SecretStr:
        """Resolve one application-owned webhook HMAC secret into memory."""
        secret_name = self._validate_webhook_secret_reference(secret_reference)

        try:
            response = await asyncio.to_thread(
                self._client.secrets.get_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_WEBHOOK_SECRET_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                raise WebhookSigningSecretVaultError(
                    "webhook_secret_not_found",
                    retryable=False,
                ) from error

            raise WebhookSigningSecretVaultError(
                "webhook_secret_resolution_failed",
                retryable=_is_retryable(error),
            ) from error

        secret_value = getattr(response, "secretValue", None)
        if not isinstance(secret_value, str) or not secret_value:
            raise WebhookSigningSecretVaultError(
                "webhook_secret_invalid",
                retryable=False,
            )

        return SecretStr(secret_value)

    async def delete_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> None:
        """Delete one application-owned webhook signing secret."""
        secret_name = self._validate_webhook_secret_reference(secret_reference)

        try:
            await asyncio.to_thread(
                self._client.secrets.delete_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_WEBHOOK_SECRET_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                return

            raise WebhookSigningSecretVaultError(
                "webhook_secret_delete_failed",
                retryable=_is_retryable(error),
            ) from error

    async def delete(self, *, credential_reference: str) -> None:
        """Delete one application-owned credential secret."""
        secret_name = self._validate_reference(credential_reference)

        try:
            await asyncio.to_thread(
                self._client.secrets.delete_secret_by_name,
                secret_name=secret_name,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=_CREDENTIAL_PATH,
            )
        except (InfisicalError, OSError, TimeoutError) as error:
            if _is_not_found(error):
                return

            raise CalendarCredentialVaultError(
                "calendar_credential_delete_failed",
                retryable=_is_retryable(error),
            ) from error
