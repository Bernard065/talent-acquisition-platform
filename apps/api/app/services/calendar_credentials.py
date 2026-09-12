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
