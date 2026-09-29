"""Provider-neutral abuse-control boundary for anonymous submissions."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class AbuseControlRejectedError(PermissionError):
    """Raised when an anonymous request fails abuse-control verification."""


class AbuseControlUnavailableError(RuntimeError):
    """Raised when abuse-control verification cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class PublicApplicationAbuseCheck:
    """
    Minimal request context required by an abuse-control provider.

    Do not persist or log raw IP addresses, user-agent values, CAPTCHA tokens,
    or provider responses. Providers may use these values transiently only.
    """

    public_job_id: UUID
    idempotency_key: str
    client_ip: str | None
    user_agent: str | None
    challenge_token: str | None


class PublicApplicationAbuseGuard(Protocol):
    """Verifies that an anonymous public application may be accepted."""

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Raise a classified error when submission must not continue."""
