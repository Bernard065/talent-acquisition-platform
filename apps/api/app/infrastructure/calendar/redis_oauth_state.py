"""Redis implementation of secure one-time calendar OAuth state storage."""

import hashlib
import json
import math
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import SecretStr
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_oauth import (
    CalendarOAuthState,
    CalendarOAuthStateError,
    CalendarOAuthStateStoreUnavailableError,
)

_GETDEL_FALLBACK_LUA = """
local value = redis.call("GET", KEYS[1])
if value then
    redis.call("DEL", KEYS[1])
end
return value
"""


class RedisCalendarOAuthStateStore:
    """
    Redis-backed, one-time OAuth state store.

    State tokens are hashed before being used in Redis keys. State payloads
    contain a short-lived PKCE verifier and must therefore remain on a private,
    authenticated Redis network with TLS enabled in production (`rediss://`).
    """

    def __init__(
        self,
        client: Redis,
        *,
        key_prefix: str = "tap:calendar:oauth-state:",
    ) -> None:
        normalized_prefix = key_prefix.strip()

        if not normalized_prefix:
            raise ValueError("OAuth state Redis key prefix is required.")

        if len(normalized_prefix) > 200:
            raise ValueError("OAuth state Redis key prefix is too long.")

        self._client = client
        self._key_prefix = normalized_prefix

    @classmethod
    def from_url(
        cls,
        redis_url: str,
        *,
        key_prefix: str = "tap:calendar:oauth-state:",
    ) -> "RedisCalendarOAuthStateStore":
        """Create a Redis state store with bounded connection timeouts."""
        client: Redis = Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
            health_check_interval=30,
        )
        return cls(client, key_prefix=key_prefix)

    async def close(self) -> None:
        """Close the owned Redis client during application shutdown."""
        await self._client.aclose()

    def _key(self, state_token: str) -> str:
        """Derive a non-reversible Redis key from the browser state token."""
        normalized_token = state_token.strip()

        if not normalized_token:
            raise CalendarOAuthStateError("Calendar OAuth state is invalid.")

        if len(normalized_token) > 1_000:
            raise CalendarOAuthStateError("Calendar OAuth state is invalid.")

        token_hash = hashlib.sha256(
            normalized_token.encode("utf-8")
        ).hexdigest()

        return f"{self._key_prefix}{token_hash}"

    @staticmethod
    def _serialize(state: CalendarOAuthState) -> str:
        """Serialize the minimum server-side OAuth state payload."""
        return json.dumps(
            {
                "tenant_id": str(state.tenant_id),
                "owner_user_id": str(state.owner_user_id),
                "provider": state.provider.value,
                "redirect_uri": state.redirect_uri,
                "code_verifier": state.code_verifier.get_secret_value(),
                "expires_at": state.expires_at.astimezone(UTC).isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _deserialize(payload: str) -> CalendarOAuthState:
        """Parse a consumed Redis payload without exposing its contents."""
        try:
            raw = cast(dict[str, object], json.loads(payload))
            expires_at = datetime.fromisoformat(str(raw["expires_at"]))

            if expires_at.tzinfo is None or expires_at.utcoffset() is None:
                raise ValueError("OAuth state expiry must be timezone-aware.")

            return CalendarOAuthState(
                tenant_id=UUID(str(raw["tenant_id"])),
                owner_user_id=UUID(str(raw["owner_user_id"])),
                provider=CalendarProvider(str(raw["provider"])),
                redirect_uri=str(raw["redirect_uri"]),
                code_verifier=SecretStr(str(raw["code_verifier"])),
                expires_at=expires_at.astimezone(UTC),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise CalendarOAuthStateError(
                "Calendar OAuth state is invalid."
            ) from error

    @staticmethod
    def _ttl_seconds(expires_at: datetime) -> int:
        """Calculate a positive whole-second TTL from the state expiry."""
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise CalendarOAuthStateError(
                "Calendar OAuth state expiry must include a UTC offset."
            )

        remaining_seconds = (
            expires_at.astimezone(UTC) - datetime.now(UTC)
        ).total_seconds()

        if remaining_seconds <= 0:
            raise CalendarOAuthStateError("Calendar OAuth state has expired.")

        return math.ceil(remaining_seconds)

    async def store(
        self,
        *,
        state_token: str,
        state: CalendarOAuthState,
    ) -> None:
        """Store one state record with a TTL derived from its expiry."""
        key = self._key(state_token)
        ttl_seconds = self._ttl_seconds(state.expires_at)

        try:
            await self._client.set(
                key,
                self._serialize(state),
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as error:
            raise CalendarOAuthStateStoreUnavailableError(
                "Calendar OAuth state storage is unavailable."
            ) from error

    async def _atomic_getdel(self, key: str) -> str | None:
        """Atomically read and delete state, with a Lua fallback for old Redis."""
        try:
            value = await cast(
                Awaitable[str | bytes | None],
                self._client.execute_command("GETDEL", key),  # type: ignore[no-untyped-call]
            )
        except ResponseError as error:
            if "unknown command" not in str(error).lower():
                raise

            value = await cast(
                Awaitable[str | bytes | None],
                self._client.eval(_GETDEL_FALLBACK_LUA, 1, key),
            )

        if value is None:
            return None

        if isinstance(value, bytes):
            return value.decode("utf-8")

        return value

    async def consume(self, *, state_token: str) -> CalendarOAuthState:
        """Atomically consume one unexpired state record."""
        key = self._key(state_token)

        try:
            payload = await self._atomic_getdel(key)
        except RedisError as error:
            raise CalendarOAuthStateStoreUnavailableError(
                "Calendar OAuth state storage is unavailable."
            ) from error

        if payload is None:
            raise CalendarOAuthStateError(
                "Calendar OAuth state is missing, expired, or already used."
            )

        state = self._deserialize(payload)

        if state.expires_at <= datetime.now(UTC):
            raise CalendarOAuthStateError("Calendar OAuth state has expired.")

        return state
