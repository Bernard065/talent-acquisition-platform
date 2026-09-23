"""Deterministic in-memory token-bucket rate limiter for tests."""

import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.services.rate_limiting import (
    RateLimitPolicy,
    RateLimitResult,
)


@dataclass(slots=True)
class _Bucket:
    """Mutable state for one key and policy combination."""

    tokens: float
    last_refilled_at: float


class InMemoryRateLimiter:
    """
    Process-local token-bucket implementation for tests.

    This is intentionally not used in production: separate API processes would
    maintain separate buckets and could not enforce a shared limit.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def consume(
        self,
        *,
        key: str,
        policy: RateLimitPolicy,
    ) -> RateLimitResult:
        """Atomically consume one token from the key's token bucket."""
        normalized_key = self._validate_key(key)
        now = self._clock()
        refill_rate = policy.limit / policy.window_seconds

        async with self._lock:
            bucket = self._buckets.get(normalized_key)

            if bucket is None:
                bucket = _Bucket(
                    tokens=float(policy.limit),
                    last_refilled_at=now,
                )
                self._buckets[normalized_key] = bucket
            else:
                elapsed_seconds = max(0.0, now - bucket.last_refilled_at)
                bucket.tokens = min(
                    float(policy.limit),
                    bucket.tokens + (elapsed_seconds * refill_rate),
                )
                bucket.last_refilled_at = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return RateLimitResult(
                    allowed=True,
                    limit=policy.limit,
                    remaining=max(0, math.floor(bucket.tokens)),
                    retry_after_seconds=None,
                )

            seconds_until_next_token = (1.0 - bucket.tokens) / refill_rate

            return RateLimitResult(
                allowed=False,
                limit=policy.limit,
                remaining=0,
                retry_after_seconds=max(
                    1,
                    math.ceil(seconds_until_next_token),
                ),
            )

    @staticmethod
    def _validate_key(key: str) -> str:
        """Reject empty or unexpectedly large keys before retaining state."""
        normalized_key = key.strip()

        if not normalized_key:
            raise ValueError("Rate-limit key must not be empty.")

        if len(normalized_key) > 512:
            raise ValueError("Rate-limit key must not exceed 512 characters.")

        return normalized_key
