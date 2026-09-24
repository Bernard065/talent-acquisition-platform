"""Redis-backed distributed token-bucket rate limiter."""

from __future__ import annotations

import hashlib
from typing import Protocol, cast

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.services.rate_limiting import (
    RateLimitPolicy,
    RateLimitResult,
    RateLimitUnavailableError,
)

_TOKEN_BUCKET_LUA = (
    """
local redis_time = redis.call("TIME")
local now = tonumber(redis_time[1]) + (tonumber(redis_time[2]) / 1000000)

local capacity = tonumber(ARGV[1])
local window_seconds = tonumber(ARGV[2])
local refill_rate = capacity / window_seconds

local values = redis.call("HMGET", KEYS[1], "tokens", "updated_at")
local tokens = tonumber(values[1])
local updated_at = tonumber(values[2])

if tokens == nil or updated_at == nil then
    tokens = capacity
    updated_at = now
else
    local elapsed = math.max(0, now - updated_at)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
end

local allowed = 0
local retry_after = 0

if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after = math.max(1, math.ceil((1 - tokens) / refill_rate))
end

local ttl_seconds = math.max(1, math.ceil(window_seconds * 2))

redis.call(
    "HSET",
    KEYS[1],
    "tokens",
    tokens,
    "updated_at",
    now
)
redis.call("EXPIRE", KEYS[1], ttl_seconds)

return {
    allowed,
    math.max(0, math.floor(tokens)),
    retry_after
}
"""  # noqa: S105 -- embedded Lua script, not a credential
)


def _coerce_redis_int(value: object) -> int:
    """Convert Redis script values into Python ints while preserving errors."""
    if isinstance(value, (int, float, str, bytes, bytearray)):
        return int(value)
    raise TypeError("Redis response value is not numeric.")


class _RedisClient(Protocol):
    """Small Redis client surface used by this adapter."""

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: object,
    ) -> object:
        """Run an atomic Lua script."""

    async def aclose(self) -> None:
        """Release the underlying Redis connection pool."""


class RedisRateLimiter:
    """
    Distributed token-bucket rate limiter.

    Keys are SHA-256 hashed before reaching Redis. This prevents identifiers
    such as IP addresses, user subjects, or tenant IDs from appearing in Redis
    key names, metrics, or operational tooling.
    """

    def __init__(
        self,
        client: _RedisClient,
        *,
        key_prefix: str = "tap:rate-limit:",
    ) -> None:
        normalized_prefix = key_prefix.strip()

        if not normalized_prefix or len(normalized_prefix) > 128:
            raise ValueError("Rate-limit key prefix is invalid.")

        self._client = client
        self._key_prefix = normalized_prefix.rstrip(":") + ":"

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        *,
        key_prefix: str = "tap:rate-limit:",
    ) -> RedisRateLimiter:
        """Construct a Redis client with bounded connection and I/O timeouts."""
        client: Redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        return cls(
            cast(_RedisClient, client),
            key_prefix=key_prefix,
        )

    async def consume(
        self,
        *,
        key: str,
        policy: RateLimitPolicy,
    ) -> RateLimitResult:
        """Atomically refill and consume one token using Redis server time."""
        redis_key = self._key(key)

        try:
            raw_result = await self._client.eval(
                _TOKEN_BUCKET_LUA,
                1,
                redis_key,
                policy.limit,
                policy.window_seconds,
            )
        except RedisError as error:
            raise RateLimitUnavailableError(
                "Rate-limit provider is unavailable."
            ) from error

        try:
            allowed_raw, remaining_raw, retry_after_raw = cast(
                tuple[object, object, object] | list[object],
                raw_result,
            )
            allowed = _coerce_redis_int(allowed_raw) == 1
            remaining = _coerce_redis_int(remaining_raw)
            retry_after = _coerce_redis_int(retry_after_raw)
        except (TypeError, ValueError):
            raise RateLimitUnavailableError(
                "Rate-limit provider returned an invalid response."
            ) from None

        if remaining < 0 or retry_after < 0:
            raise RateLimitUnavailableError(
                "Rate-limit provider returned an invalid response."
            )

        return RateLimitResult(
            allowed=allowed,
            limit=policy.limit,
            remaining=remaining,
            retry_after_seconds=None if allowed else max(1, retry_after),
        )

    async def close(self) -> None:
        """Release the Redis connection pool during application shutdown."""
        try:
            await self._client.aclose()
        except RedisError as error:
            raise RateLimitUnavailableError(
                "Rate-limit provider could not be closed cleanly."
            ) from error

    def _key(self, key: str) -> str:
        """Return one bounded, namespaced, non-PII Redis key."""
        normalized_key = key.strip()

        if not normalized_key:
            raise ValueError("Rate-limit key must not be empty.")

        if len(normalized_key) > 512:
            raise ValueError("Rate-limit key must not exceed 512 characters.")

        fingerprint = hashlib.sha256(
            normalized_key.encode("utf-8")
        ).hexdigest()

        return f"{self._key_prefix}{fingerprint}"
