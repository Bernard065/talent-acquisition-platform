"""Unit tests for Redis-backed one-time calendar OAuth state."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from app.domains.calendar.enums import CalendarProvider
from app.infrastructure.calendar.redis_oauth_state import (
    RedisCalendarOAuthStateStore,
)
from app.services.calendar_oauth import (
    CalendarOAuthState,
    CalendarOAuthStateError,
    CalendarOAuthStateStoreUnavailableError,
)


@dataclass
class _FakeRedis:
    """Minimal Redis double supporting commands used by the state adapter."""

    values: dict[str, str] = field(default_factory=dict)
    set_calls: list[dict[str, object]] = field(default_factory=list)
    execute_calls: list[tuple[object, ...]] = field(default_factory=list)
    eval_calls: list[tuple[object, ...]] = field(default_factory=list)
    unavailable: bool = False
    getdel_unsupported: bool = False
    closed: bool = False

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool | None:
        """Record one TTL-bound Redis SET operation."""
        if self.unavailable:
            raise RedisConnectionError("redis unavailable")

        self.set_calls.append(
            {
                "key": key,
                "value": value,
                "ex": ex,
                "nx": nx,
            }
        )

        if nx and key in self.values:
            return None

        self.values[key] = value
        return True

    async def execute_command(self, *args: object) -> str | None:
        """Implement Redis GETDEL or simulate an unsupported command."""
        if self.unavailable:
            raise RedisConnectionError("redis unavailable")

        self.execute_calls.append(args)

        if self.getdel_unsupported:
            raise ResponseError("unknown command 'GETDEL'")

        _, key = args
        return self.values.pop(str(key), None)

    async def eval(
        self,
        script: str,
        key_count: int,
        key: str,
    ) -> str | None:
        """Implement the adapter's atomic Lua GET-and-delete fallback."""
        if self.unavailable:
            raise RedisConnectionError("redis unavailable")

        self.eval_calls.append((script, key_count, key))
        return self.values.pop(key, None)

    async def aclose(self) -> None:
        """Record managed-client shutdown."""
        self.closed = True


def _state(
    *,
    expires_at: datetime | None = None,
) -> CalendarOAuthState:
    """Build one valid short-lived server-side OAuth state record."""
    return CalendarOAuthState(
        tenant_id=uuid4(),
        owner_user_id=uuid4(),
        provider=CalendarProvider.GOOGLE,
        redirect_uri="http://localhost:3000/oauth/calendar/callback",
        code_verifier=SecretStr("server-side-pkce-verifier"),
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=5),
    )


def _store(fake_redis: _FakeRedis) -> RedisCalendarOAuthStateStore:
    """Construct the adapter with the in-memory Redis double."""
    return RedisCalendarOAuthStateStore(
        cast(Redis, fake_redis),
        key_prefix="tap:test:calendar-oauth:",
    )


@pytest.mark.asyncio
async def test_hashes_browser_state_before_using_it_as_redis_key() -> None:
    """Never expose raw browser state tokens in Redis key names."""
    fake_redis = _FakeRedis()
    store = _store(fake_redis)
    state_token = "browser-state-token-that-must-not-appear-in-redis-key"  # noqa: S105

    await store.store(
        state_token=state_token,
        state=_state(),
    )

    assert len(fake_redis.set_calls) == 1

    call = fake_redis.set_calls[0]
    redis_key = str(call["key"])

    assert redis_key.startswith("tap:test:calendar-oauth:")
    assert state_token not in redis_key
    assert len(redis_key.rsplit(":", maxsplit=1)[1]) == 64
    assert call["nx"] is True
    assert isinstance(call["ex"], int)
    assert int(call["ex"]) > 0

    stored_payload = str(call["value"])
    assert state_token not in stored_payload
    assert "server-side-pkce-verifier" in stored_payload


@pytest.mark.asyncio
async def test_rejects_expired_state_without_writing_to_redis() -> None:
    """Do not persist an OAuth state record whose expiry has already passed."""
    fake_redis = _FakeRedis()
    store = _store(fake_redis)

    with pytest.raises(CalendarOAuthStateError, match="expired"):
        await store.store(
            state_token="expired-state-token",  # noqa: S106
            state=_state(
                expires_at=datetime.now(UTC) - timedelta(seconds=1)
            ),
        )

    assert not fake_redis.set_calls


@pytest.mark.asyncio
async def test_consumes_state_atomically_once() -> None:
    """Only the first callback can retrieve the stored OAuth state."""
    fake_redis = _FakeRedis()
    store = _store(fake_redis)
    original = _state()
    state_token = "single-use-state-token"  # noqa: S105

    await store.store(state_token=state_token, state=original)
    consumed = await store.consume(state_token=state_token)

    assert consumed.tenant_id == original.tenant_id
    assert consumed.owner_user_id == original.owner_user_id
    assert consumed.provider is CalendarProvider.GOOGLE
    assert (
        consumed.code_verifier.get_secret_value()
        == original.code_verifier.get_secret_value()
    )
    assert len(fake_redis.execute_calls) == 1

    with pytest.raises(CalendarOAuthStateError, match="missing"):
        await store.consume(state_token=state_token)  # noqa: S106


@pytest.mark.asyncio
async def test_uses_lua_fallback_when_getdel_is_not_supported() -> None:
    """Retain atomic consume behavior with older Redis server versions."""
    fake_redis = _FakeRedis(getdel_unsupported=True)
    store = _store(fake_redis)
    state_token = "lua-fallback-state-token"  # noqa: S105

    await store.store(state_token=state_token, state=_state())
    consumed = await store.consume(state_token=state_token)

    assert consumed.provider is CalendarProvider.GOOGLE
    assert len(fake_redis.execute_calls) == 1
    assert len(fake_redis.eval_calls) == 1

    with pytest.raises(CalendarOAuthStateError, match="missing"):
        await store.consume(state_token=state_token)  # noqa: S106


@pytest.mark.asyncio
async def test_rejects_malformed_consumed_state() -> None:
    """Treat malformed Redis data as invalid state without exposing details."""
    fake_redis = _FakeRedis()
    store = _store(fake_redis)
    state_token = "malformed-state-token"  # noqa: S105

    fake_redis.values[store._key(state_token)] = "{not-json"  # pylint: disable=protected-access

    with pytest.raises(CalendarOAuthStateError, match="invalid"):
        await store.consume(state_token=state_token)

    assert not fake_redis.values


@pytest.mark.asyncio
async def test_maps_redis_unavailability_without_leaking_provider_details() -> None:
    """Fail closed when state cannot be stored or atomically consumed."""
    unavailable_redis = _FakeRedis(unavailable=True)
    store = _store(unavailable_redis)

    with pytest.raises(CalendarOAuthStateStoreUnavailableError):
        await store.store(
            state_token="unavailable-state-token",  # noqa: S106
            state=_state(),
        )

    with pytest.raises(CalendarOAuthStateStoreUnavailableError):
        await store.consume(state_token="unavailable-state-token")  # noqa: S106


@pytest.mark.asyncio
async def test_closes_owned_redis_client() -> None:
    """Release the Redis client during application shutdown."""
    fake_redis = _FakeRedis()
    store = _store(fake_redis)

    await store.close()

    assert fake_redis.closed is True
