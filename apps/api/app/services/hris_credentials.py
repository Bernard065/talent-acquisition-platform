"""External secret-vault contracts for HRIS connection credentials."""

from collections.abc import Mapping
from dataclasses import dataclass
from re import compile as re_compile
from typing import Protocol

from pydantic import SecretStr

_CREDENTIAL_NAME_PATTERN = re_compile(r"^[a-z][a-z0-9_]{0,63}$")


class HrisCredentialVaultError(RuntimeError):
    """Classified error while storing, resolving, or deleting HRIS credentials."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class HrisCredentials:
    """
    Validated in-memory provider credentials.

    Values must be sent only to the external vault or a future HRIS provider
    adapter. They must never be persisted in PostgreSQL, logs, audit records,
    or outbox payloads.
    """

    values: Mapping[str, SecretStr]

    def __post_init__(self) -> None:
        if not self.values or len(self.values) > 32:
            raise ValueError(
                "HRIS credentials must contain between one and 32 values."
            )

        normalized: dict[str, SecretStr] = {}

        for name, value in self.values.items():
            if (
                not isinstance(name, str)
                or not _CREDENTIAL_NAME_PATTERN.fullmatch(name)
                or not isinstance(value, SecretStr)
                or not value.get_secret_value()
            ):
                raise ValueError("HRIS credentials are invalid.")

            normalized[name] = value

        object.__setattr__(self, "values", normalized)


class HrisCredentialVault(Protocol):
    """External vault boundary for tenant-owned HRIS credentials."""

    async def store_hris_credentials(
        self,
        *,
        provider: str,
        tenant_id: str,
        credentials: HrisCredentials,
    ) -> str:
        """Store credentials and return only an opaque reference."""

    async def resolve_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> HrisCredentials:
        """Resolve credentials only in memory for a future worker."""

    async def delete_hris_credentials(
        self,
        *,
        credential_reference: str,
    ) -> None:
        """Delete an application-owned HRIS credential secret."""
