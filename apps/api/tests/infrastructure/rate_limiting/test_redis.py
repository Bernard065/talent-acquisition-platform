"""Tests for the Redis-backed distributed rate-limit adapter."""

import pytest

from app.infrastructure.rate_limiting.redis import RedisRateLimiter
from app.services.rate_limiting import (
    RateLimitPolicy,
    RateLimitUnavailableError,
)


class _FakeRedisClient:
    """Minimal Redis client with a deterministic Lua response."""

    def __init__(self, result: object) -> None:
        self.result = result

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        """Return the prerecorded Lua script result for the test."""
        del script, numkeys, keys_and_args
        return self.result

    async def aclose(self) -> None:
        """No-op close for test clients."""


@pytest.mark.asyncio
async def test_consume_parses_redis_lua_result() -> None:
    """The adapter converts the Lua script tuple into a typed result."""
    limiter = RedisRateLimiter(_FakeRedisClient((1, 0, 0)))
    policy = RateLimitPolicy(limit=2, window_seconds=10)

    result = await limiter.consume(
        key="tap:test:public-jobs",
        policy=policy,
    )

    assert result.allowed is True
    assert result.limit == 2
    assert result.remaining == 0
    assert result.retry_after_seconds is None


@pytest.mark.asyncio
async def test_consume_rejects_invalid_redis_response() -> None:
    """Malformed Redis data is surfaced as an unavailable provider error."""
    limiter = RedisRateLimiter(_FakeRedisClient(("invalid", "still-invalid", 0)))
    policy = RateLimitPolicy(limit=2, window_seconds=10)

    with pytest.raises(RateLimitUnavailableError, match="invalid response"):
        await limiter.consume(
            key="tap:test:public-jobs",
            policy=policy,
        )
