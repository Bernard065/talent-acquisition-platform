"""Infisical Cloud implementation of the calendar credential vault."""

from __future__ import annotations

import json
from collections.abc import Mapping
from uuid import uuid4

import structlog
from infisical_sdk import (  # type: ignore[import-untyped]
    InfisicalError,
    InfisicalSDKClient,
)
from pydantic import SecretStr

from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    ResolvedCalendarCredentials,
)

logger = structlog.get_logger()


class InfisicalCredentialVault:
    """Store and resolve calendar OAuth credentials via Infisical Cloud.

    Satisfies both ``CalendarCredentialVault`` (store / delete) and
    ``CalendarCredentialResolver`` (resolve) structural protocols.

    Each credential set is stored as a single Infisical secret whose value
    is a JSON-serialised mapping of token fields.  Secret names follow::

        calendar-creds-{provider}-{tenant_id}-{owner_user_id}-{uuid4}

    The secret name is the opaque ``credential_reference`` persisted in
    the application database.
    """

    _CREDENTIAL_PATH = "/calendar-credentials/"  # noqa: S105

    def __init__(
        self,
        *,
        project_id: str,
        environment_slug: str,
        client: InfisicalSDKClient | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._project_id = project_id
        self._environment_slug = environment_slug

        if client is not None:
            self._client = client
        else:
            if client_id is None or client_secret is None:
                raise ValueError(
                    "client_id and client_secret are required "
                    "when no pre-configured client is provided"
                )

            self._client = InfisicalSDKClient(host="https://app.infisical.com")
            self._client.auth.universal_auth.login(
                client_id=client_id,
                client_secret=client_secret,
            )

    # -- CalendarCredentialVault ------------------------------------------

    async def store(
        self,
        *,
        provider: str,
        tenant_id: str,
        owner_user_id: str,
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        """Persist credentials as a new secret and return the opaque reference."""
        secret_name = f"calendar-creds-{provider}-{tenant_id}-{owner_user_id}-{uuid4()}"

        payload = json.dumps(
            {k: v.get_secret_value() for k, v in credentials.values.items()},
        )

        self._client.secrets.create_secret_by_name(
            secret_name=secret_name,
            secret_value=payload,
            project_id=self._project_id,
            environment_slug=self._environment_slug,
            secret_path=self._CREDENTIAL_PATH,
        )

        logger.info(
            "calendar_credential_stored",
            provider=provider,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
        )

        return secret_name

    async def delete(self, *, credential_reference: str) -> None:
        """Delete the secret identified by *credential_reference*."""
        try:
            self._client.secrets.delete_secret_by_name(
                secret_name=credential_reference,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=self._CREDENTIAL_PATH,
            )
            logger.info(
                "calendar_credential_deleted",
                credential_reference=credential_reference,
            )
        except InfisicalError:
            # Infisical raises on not-found; treat delete as idempotent.
            logger.warning(
                "calendar_credential_delete_failed",
                credential_reference=credential_reference,
            )

    # -- CalendarCredentialResolver --------------------------------------

    async def resolve(
        self,
        *,
        credential_reference: str,
    ) -> ResolvedCalendarCredentials:
        """Resolve the latest version of a stored credential."""
        try:
            secret = self._client.secrets.get_secret_by_name(
                secret_name=credential_reference,
                project_id=self._project_id,
                environment_slug=self._environment_slug,
                secret_path=self._CREDENTIAL_PATH,
            )
        except InfisicalError as exc:
            error_message = str(exc).lower()
            retryable = "not found" not in error_message
            raise CalendarCredentialResolutionError(
                "calendar_credential_not_found"
                if not retryable
                else "calendar_credential_resolution_failed",
                retryable=retryable,
            ) from exc

        raw: Mapping[str, str] = json.loads(secret.secretValue)

        return ResolvedCalendarCredentials(
            values={k: SecretStr(v) for k, v in raw.items()},
        )
