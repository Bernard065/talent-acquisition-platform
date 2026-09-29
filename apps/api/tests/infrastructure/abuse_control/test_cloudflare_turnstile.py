"""Tests for Cloudflare Turnstile verification without live network calls."""

from urllib.parse import parse_qs
from uuid import UUID

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.abuse_control.cloudflare_turnstile import (
    CloudflareTurnstileAbuseGuard,
)
from app.services.abuse_control import (
    AbuseControlRejectedError,
    AbuseControlUnavailableError,
    PublicApplicationAbuseCheck,
)

_JOB_ID = UUID("f32eb4be-9943-4bcc-a53b-60f6672ce033")
_VALID_CHALLENGE = "turnstile-token"
_UNLOGGED_CHALLENGE = "never-log-this-token"


def _check(
    *,
    token: str | None = _VALID_CHALLENGE,
    key: str = "public-application-1",
) -> PublicApplicationAbuseCheck:
    return PublicApplicationAbuseCheck(
        public_job_id=_JOB_ID,
        idempotency_key=key,
        client_ip="192.0.2.10",
        user_agent="test-agent",
        challenge_token=token,
    )


@pytest.mark.asyncio
async def test_validates_with_cloudflare_and_uses_stable_provider_key() -> None:
    """Send the challenge and a stable derived idempotency key to Cloudflare."""
    bodies: list[dict[str, list[str]]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(parse_qs((await request.aread()).decode()))
        return httpx.Response(
            200,
            json={
                "success": True,
                "hostname": "careers.example.com",
                "action": "public_application",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        guard = CloudflareTurnstileAbuseGuard(
            secret_key=SecretStr("test-secret"),
            expected_hostnames=frozenset({"careers.example.com"}),
            expected_action="public_application",
            http_client=client,
        )
        await guard.verify(_check())
        await guard.verify(_check())

    assert len(bodies) == 2
    assert bodies[0]["secret"] == ["test-secret"]
    assert bodies[0]["response"] == ["turnstile-token"]
    assert bodies[0]["idempotency_key"] == bodies[1]["idempotency_key"]
    UUID(bodies[0]["idempotency_key"][0])
    assert "remoteip" not in bodies[0]


@pytest.mark.asyncio
async def test_rejects_missing_or_invalid_challenge() -> None:
    """Reject absent challenges and provider-reported invalid tokens."""
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": False,
                "error-codes": ["invalid-input-response"],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        guard = CloudflareTurnstileAbuseGuard(
            secret_key=SecretStr("test-secret"),
            expected_hostnames=frozenset({"careers.example.com"}),
            expected_action="public_application",
            http_client=client,
        )

        with pytest.raises(AbuseControlRejectedError):
            await guard.verify(_check(token=None))

        with pytest.raises(AbuseControlRejectedError):
            await guard.verify(_check())


@pytest.mark.asyncio
async def test_rejects_hostname_or_action_mismatch() -> None:
    """Reject successful verifications for an unexpected hostname or action."""
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "hostname": "attacker.example",
                "action": "public_application",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        guard = CloudflareTurnstileAbuseGuard(
            secret_key=SecretStr("test-secret"),
            expected_hostnames=frozenset({"careers.example.com"}),
            expected_action="public_application",
            http_client=client,
        )
        with pytest.raises(AbuseControlRejectedError):
            await guard.verify(_check())


@pytest.mark.asyncio
async def test_provider_outage_fails_closed_without_leaking_token_or_secret() -> None:
    """Treat provider outages as unavailable without exposing request secrets."""
    async def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated outage")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
    ) as client:
        guard = CloudflareTurnstileAbuseGuard(
            secret_key=SecretStr("never-log-this-secret"),
            expected_hostnames=frozenset({"careers.example.com"}),
            expected_action="public_application",
            http_client=client,
        )
        with pytest.raises(AbuseControlUnavailableError) as error:
            await guard.verify(_check(token=_UNLOGGED_CHALLENGE))

    assert "never-log-this-secret" not in str(error.value)
    assert "never-log-this-token" not in str(error.value)
