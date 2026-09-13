"""Google Secret Manager implementation of the calendar credential vault."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from google.api_core.exceptions import GoogleAPICallError, NotFound
from google.cloud.secretmanager_v1 import (
    AccessSecretVersionRequest,
    AddSecretVersionRequest,
    CreateSecretRequest,
    DeleteSecretRequest,
    Secret,
    SecretPayload,
)
from pydantic import SecretStr

from app.services.calendar_credentials import (
    CalendarCredentialResolutionError,
    ResolvedCalendarCredentials,
)

if TYPE_CHECKING:
    from google.cloud.secretmanager_v1 import SecretManagerServiceClient

logger = structlog.get_logger()


class GoogleSecretManagerCredentialVault:
    """Store and resolve calendar OAuth credentials via Google Secret Manager.

    Satisfies both ``CalendarCredentialVault`` (store / delete) and
    ``CalendarCredentialResolver`` (resolve) structural protocols.

    Secrets are named::

        calendar-creds/{provider}/{tenant_id}/{owner_user_id}/{uuid4}

    The full resource name ``projects/{project}/secrets/{name}`` is the
    opaque ``credential_reference`` persisted in the application database.
    """

    def __init__(
        self,
        *,
        project_id: str,
        client: SecretManagerServiceClient | None = None,
    ) -> None:
        self._project_id = project_id

        if client is not None:
            self._client = client
        else:
            from google.cloud.secretmanager_v1 import (
                SecretManagerServiceClient as _Client,
            )

            self._client = _Client()

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
        secret_id = (
            f"calendar-creds-{provider}-{tenant_id}-{owner_user_id}-{uuid4()}"
        )
        parent = f"projects/{self._project_id}"

        self._client.create_secret(
            request=CreateSecretRequest(
                parent=parent,
                secret_id=secret_id,
                secret=Secret(
                    replication={"automatic": {}},
                    labels={
                        "provider": provider,
                        "component": "calendar",
                    },
                ),
            ),
        )

        payload = json.dumps(
            {k: v.get_secret_value() for k, v in credentials.values.items()},
        ).encode("utf-8")

        secret_name = f"{parent}/secrets/{secret_id}"

        self._client.add_secret_version(
            request=AddSecretVersionRequest(
                parent=secret_name,
                payload=SecretPayload(data=payload),
            ),
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
            self._client.delete_secret(
                request=DeleteSecretRequest(name=credential_reference),
            )
            logger.info(
                "calendar_credential_deleted",
                credential_reference=credential_reference,
            )
        except NotFound:
            logger.warning(
                "calendar_credential_delete_not_found",
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
            response = self._client.access_secret_version(
                request=AccessSecretVersionRequest(
                    name=f"{credential_reference}/versions/latest",
                ),
            )
        except NotFound:
            raise CalendarCredentialResolutionError(
                "calendar_credential_not_found",
                retryable=False,
            )
        except GoogleAPICallError as exc:
            retryable = getattr(exc, "grpc_status_code", None) is not None
            raise CalendarCredentialResolutionError(
                "calendar_credential_resolution_failed",
                retryable=retryable,
            ) from exc

        raw: Mapping[str, str] = json.loads(
            response.payload.data.decode("utf-8"),
        )

        return ResolvedCalendarCredentials(
            values={k: SecretStr(v) for k, v in raw.items()},
        )
