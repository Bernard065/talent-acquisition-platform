"""Unit tests for the Google Calendar OAuth provider adapter."""

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.calendar.google_oauth import GoogleCalendarOAuthProvider
from app.services.calendar_oauth import (
    CalendarAuthorizationRequest,
    CalendarOAuthCodeExchange,
    CalendarOAuthError,
)


def _make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[GoogleCalendarOAuthProvider, httpx.AsyncClient]:
    """Build an adapter backed by an in-memory HTTP transport."""
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://google.test",
    )
    provider = GoogleCalendarOAuthProvider(
        client_id="google-client-id",
        client_secret=SecretStr("google-client-secret"),
        http_client=client,
    )
    return provider, client


@pytest.mark.asyncio
async def test_creates_authorization_url_with_pkce_and_offline_access() -> None:
    """The browser URL contains only public OAuth and PKCE values."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Authorization URL generation must not call HTTP.")

    provider, client = _make_provider(handler)

    try:
        authorization_url = await provider.create_authorization_url(
            request=CalendarAuthorizationRequest(
                state_token="opaque-state-token",  # noqa: S106
                redirect_uri="https://app.example.com/api/v1/calendar/callback",
                code_challenge="pkce-s256-challenge",
            )
        )
    finally:
        await client.aclose()

    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.google.com"
    assert parsed.path == "/o/oauth2/v2/auth"
    assert query["client_id"] == ["google-client-id"]
    assert query["response_type"] == ["code"]
    assert query["state"] == ["opaque-state-token"]
    assert query["redirect_uri"] == [
        "https://app.example.com/api/v1/calendar/callback"
    ]
    assert query["code_challenge"] == ["pkce-s256-challenge"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["access_type"] == ["offline"]
    assert query["include_granted_scopes"] == ["true"]
    assert query["scope"] == ["https://www.googleapis.com/auth/calendar.events"]


@pytest.mark.asyncio
async def test_exchanges_code_for_in_memory_credentials() -> None:
    """A successful token exchange returns credentials without persistence."""
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            status_code=200,
            json={
                "access_token": "access-token-value",
                "refresh_token": "refresh-token-value",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    provider, client = _make_provider(handler)

    try:
        credentials = await provider.exchange_code(
            exchange=CalendarOAuthCodeExchange(
                authorization_code=SecretStr("authorization-code"),
                redirect_uri="https://app.example.com/api/v1/calendar/callback",
                code_verifier=SecretStr("server-side-pkce-verifier"),
            )
        )
    finally:
        await client.aclose()

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert str(captured_request.url) == "https://oauth2.googleapis.com/token"

    submitted = parse_qs(captured_request.content.decode("utf-8"))
    assert submitted["client_id"] == ["google-client-id"]
    assert submitted["client_secret"] == ["google-client-secret"]
    assert submitted["code"] == ["authorization-code"]
    assert submitted["code_verifier"] == ["server-side-pkce-verifier"]
    assert submitted["grant_type"] == ["authorization_code"]
    assert submitted["redirect_uri"] == [
        "https://app.example.com/api/v1/calendar/callback"
    ]

    assert credentials.values["access_token"].get_secret_value() == "access-token-value"
    assert credentials.values["refresh_token"].get_secret_value() == "refresh-token-value"
    assert credentials.values["token_type"].get_secret_value() == "Bearer"
    assert credentials.values["expires_in_seconds"].get_secret_value() == "3600"


@pytest.mark.asyncio
async def test_rejects_token_response_without_refresh_token() -> None:
    """A connection cannot be created without durable refresh credentials."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "access-token-value",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarOAuthError) as error:
            await provider.exchange_code(
                exchange=CalendarOAuthCodeExchange(
                    authorization_code=SecretStr("authorization-code"),
                    redirect_uri="https://app.example.com/api/v1/calendar/callback",
                    code_verifier=SecretStr("pkce-verifier"),
                )
            )
    finally:
        await client.aclose()

    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_rejects_invalid_token_expiry() -> None:
    """The provider rejects unusable token expiry values."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=200,
            json={
                "access_token": "access-token-value",
                "refresh_token": "refresh-token-value",
                "token_type": "Bearer",
                "expires_in": "not-a-number",
            },
        )

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarOAuthError) as error:
            await provider.exchange_code(
                exchange=CalendarOAuthCodeExchange(
                    authorization_code=SecretStr("authorization-code"),
                    redirect_uri="https://app.example.com/api/v1/calendar/callback",
                    code_verifier=SecretStr("pkce-verifier"),
                )
            )
    finally:
        await client.aclose()

    assert error.value.retryable is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [
        (400, False),
        (401, False),
        (429, True),
        (500, True),
        (503, True),
    ],
)
async def test_classifies_google_token_errors(
    status_code: int,
    retryable: bool,
) -> None:
    """Only transient provider failures are safe to retry."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            json={"error": "provider_error"},
        )

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarOAuthError) as error:
            await provider.exchange_code(
                exchange=CalendarOAuthCodeExchange(
                    authorization_code=SecretStr("authorization-code"),
                    redirect_uri="https://app.example.com/api/v1/calendar/callback",
                    code_verifier=SecretStr("pkce-verifier"),
                )
            )
    finally:
        await client.aclose()

    assert error.value.retryable is retryable


@pytest.mark.asyncio
async def test_classifies_timeout_as_retryable() -> None:
    """Transport timeouts do not consume the one-time OAuth callback."""

    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout")

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarOAuthError) as error:
            await provider.exchange_code(
                exchange=CalendarOAuthCodeExchange(
                    authorization_code=SecretStr("authorization-code"),
                    redirect_uri="https://app.example.com/api/v1/calendar/callback",
                    code_verifier=SecretStr("pkce-verifier"),
                )
            )
    finally:
        await client.aclose()

    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_rejects_insecure_redirect_before_http_call() -> None:
    """Only HTTPS redirects, plus local development HTTP, are allowed."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=500)

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarOAuthError) as error:
            await provider.create_authorization_url(
                request=CalendarAuthorizationRequest(
                    state_token="opaque-state-token",  # noqa: S106
                    redirect_uri="http://evil.example.com/oauth/callback",
                    code_challenge="pkce-s256-challenge",
                )
            )
    finally:
        await client.aclose()

    assert call_count == 0
    assert error.value.code == "google_oauth_redirect_uri_invalid"
    assert error.value.retryable is False
