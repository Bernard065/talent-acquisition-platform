"""External secret-storage contract for outbound webhook signing keys."""

from typing import Protocol

from pydantic import SecretStr


class WebhookSigningSecretVaultError(RuntimeError):
    """A classified failure while storing or deleting a webhook signing secret."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class WebhookSigningSecretVault(Protocol):
    """
    Store opaque webhook signing secrets outside PostgreSQL.

    References returned by this port may be persisted. Secret values must never
    be returned by an API, logged, audited, or inserted into an outbox payload.
    """

    async def store_webhook_signing_secret(
        self,
        *,
        secret: SecretStr,
    ) -> str:
        """Store one signing secret and return an opaque application-owned ref."""

    async def delete_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> None:
        """Delete a previously stored application-owned signing secret."""

    async def resolve_webhook_signing_secret(
        self,
        *,
        secret_reference: str,
    ) -> SecretStr:
        """Resolve one signing secret only for an outbound delivery."""
