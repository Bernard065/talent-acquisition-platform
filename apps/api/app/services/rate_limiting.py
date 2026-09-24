"""Provider-neutral rate-limiting contracts."""

from dataclasses import dataclass
from typing import Protocol


class RateLimitUnavailableError(RuntimeError):
    """Raised when the configured rate-limit provider cannot be reached."""


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    """A bounded token-bucket policy for one independently scoped key."""

    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 100_000:
            raise ValueError("Rate limit must be between 1 and 100000.")

        if not 1 <= self.window_seconds <= 86_400:
            raise ValueError(
                "Rate-limit window must be between 1 and 86400 seconds."
            )


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    """The result of atomically consuming one rate-limit token."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int | None


class RateLimiter(Protocol):
    """A distributed-safe rate-limit boundary."""

    async def consume(
        self,
        *,
        key: str,
        policy: RateLimitPolicy,
    ) -> RateLimitResult:
        """Atomically consume one token for a namespaced, non-empty key."""
