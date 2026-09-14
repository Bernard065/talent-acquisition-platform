"""Secret-reference resolution contract for calendar integrations."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from pydantic import SecretStr


class CalendarCredentialResolutionError(RuntimeError):
    """A classified failure while resolving calendar credentials."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class CalendarCredentialVaultError(RuntimeError):
    """A classified failure while storing or deleting calendar credentials."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class ResolvedCalendarCredentials:
    """
    Provider-specific credentials held only in memory.

    Values originate from a secret manager through an opaque
    `credential_reference`. They must never be persisted in application
    tables, returned by HTTP APIs, inserted into outbox payloads, or logged.
    """

    values: Mapping[str, SecretStr]

    def required(self, name: str) -> SecretStr:
        """Return one required secret without exposing it in an error message."""
        value = self.values.get(name)
        if value is None:
            raise CalendarCredentialResolutionError(
                "calendar_credential_field_missing",
                retryable=False,
            )

        return value


class CalendarCredentialResolver(Protocol):
    """Resolve opaque calendar credential references through a secret manager."""

    async def resolve(
        self,
        *,
        credential_reference: str,
    ) -> ResolvedCalendarCredentials:
        """Resolve credentials into memory only for one provider operation."""


class CalendarCredentialVault(Protocol):
    """
    Store provider credentials outside the application database.

    Implementations may use a cloud secret manager, HSM-backed vault, or an
    encrypted internal secret service. They return only an opaque reference
    suitable for persistence in `CalendarConnection.credential_reference`.
    """

    async def store(
        self,
        *,
        provider: str,
        tenant_id: str,
        owner_user_id: str,
        credentials: ResolvedCalendarCredentials,
    ) -> str:
        """Persist credentials externally and return an opaque reference."""

    async def delete(self, *, credential_reference: str) -> None:
        """Delete or revoke the externally stored credential material."""
