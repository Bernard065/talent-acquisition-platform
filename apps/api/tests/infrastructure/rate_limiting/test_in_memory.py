"""Tests for the deterministic in-memory rate-limit adapter."""

import asyncio

import pytest

from app.infrastructure.rate_limiting.in_memory import InMemoryRateLimiter
from app.services.rate_limiting import RateLimitPolicy


class _Clock:
    """Controllable monotonic clock used by token-bucket tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.mark.asyncio
async def test_allows_until_capacity_then_returns_retry_after() -> None:
    """A bucket rejects the request after its configured capacity is consumed."""
    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(limit=2, window_seconds=10)

    first = await limiter.consume(key="tap:test:public-jobs", policy=policy)
    second = await limiter.consume(key="tap:test:public-jobs", policy=policy)
    rejected = await limiter.consume(
        key="tap:test:public-jobs",
        policy=policy,
    )

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0

    assert rejected.allowed is False
    assert rejected.limit == 2
    assert rejected.remaining == 0
    assert rejected.retry_after_seconds == 5


@pytest.mark.asyncio
async def test_refills_tokens_over_time() -> None:
    """Consumed capacity returns gradually rather than resetting abruptly."""
    clock = _Clock()
    limiter = InMemoryRateLimiter(clock=clock)
    policy = RateLimitPolicy(limit=2, window_seconds=10)

    await limiter.consume(key="tap:test:callbacks", policy=policy)
    await limiter.consume(key="tap:test:callbacks", policy=policy)

    clock.now = 5.0
    refilled = await limiter.consume(
        key="tap:test:callbacks",
        policy=policy,
    )

    assert refilled.allowed is True
    assert refilled.remaining == 0


@pytest.mark.asyncio
async def test_keys_are_independently_limited() -> None:
    """One principal or route cannot consume another key's capacity."""
    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(limit=1, window_seconds=60)

    first_key = await limiter.consume(key="tap:test:key-a", policy=policy)
    second_key = await limiter.consume(key="tap:test:key-b", policy=policy)
    exhausted_first_key = await limiter.consume(
        key="tap:test:key-a",
        policy=policy,
    )

    assert first_key.allowed is True
    assert second_key.allowed is True
    assert exhausted_first_key.allowed is False


@pytest.mark.asyncio
async def test_concurrent_consumers_cannot_exceed_bucket_capacity() -> None:
    """The adapter serializes concurrent token consumption safely."""
    limiter = InMemoryRateLimiter()
    policy = RateLimitPolicy(limit=3, window_seconds=60)

    results = await asyncio.gather(
        *(
            limiter.consume(
                key="tap:test:concurrent",
                policy=policy,
            )
            for _ in range(10)
        )
    )

    assert sum(result.allowed for result in results) == 3
    assert sum(not result.allowed for result in results) == 7


def test_rejects_invalid_policy_and_key() -> None:
    """Reject invalid configuration and unsafe key inputs early."""
    with pytest.raises(ValueError, match="Rate limit"):
        RateLimitPolicy(limit=0, window_seconds=60)

    with pytest.raises(ValueError, match="window"):
        RateLimitPolicy(limit=1, window_seconds=0)
