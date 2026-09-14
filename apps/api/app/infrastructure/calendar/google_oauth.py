"""Google Calendar OAuth provider adapter."""

from collections.abc import Sequence
from json import JSONDecodeError
from urllib.parse import urlencode, urlparse

import httpx
from pydantic import SecretStr

from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_credentials import ResolvedCalendarCredentials
from app.services.calendar_oauth import (
    CalendarAuthorizationRequest,
    CalendarOAuthCodeExchange,
    CalendarOAuthError,
)

_GOOGLE_AUTHORIZATION_ENDPOINT = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)
_GOOGLE_TOKEN_ENDPOINT = (
    "https://oauth2.googleapis.com/token"  # noqa: S105
)
_GOOGLE_CALENDAR_EVENTS_SCOPE = (
    "https://www.googleapis.com/auth/calendar.events"
)
_MAX_TOKEN_EXPIRY_SECONDS = 86_400


def _validate_redirect_uri(redirect_uri: str) -> None:
    """Permit HTTPS callbacks and local HTTP callbacks only."""
    parsed = urlparse(redirect_uri)

    if parsed.scheme == "https" and parsed.netloc:
        return

    if (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        return

    raise CalendarOAuthError(
        "google_oauth_redirect_uri_invalid",
        retryable=False,
    )


def _is_retryable_http_status(status_code: int) -> bool:
    """Return whether a provider response can safely be retried."""
    return status_code == 408 or status_code == 429 or status_code >= 500


class GoogleCalendarOAuthProvider:
    """
    Google authorization-code OAuth adapter with PKCE.

    OAuth client credentials are injected by runtime configuration. They are
    never accepted from an HTTP request, stored in PostgreSQL, or logged.
    """

    provider = CalendarProvider.GOOGLE

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        http_client: httpx.AsyncClient,
        scopes: Sequence[str] = (_GOOGLE_CALENDAR_EVENTS_SCOPE,),
    ) -> None:
        normalized_client_id = client_id.strip()
        if not normalized_client_id:
            raise ValueError("Google OAuth client ID must not be empty.")

        normalized_scopes = tuple(
            scope.strip()
            for scope in scopes
            if scope.strip()
        )
        if not normalized_scopes:
            raise ValueError("At least one Google OAuth scope is required.")

        self._client_id = normalized_client_id
        self._client_secret = client_secret
        self._http_client = http_client
        self._scopes = normalized_scopes

    async def create_authorization_url(
        self,
        *,
        request: CalendarAuthorizationRequest,
    ) -> str:
        """Create a Google authorization URL for one server-stored PKCE state."""
        _validate_redirect_uri(request.redirect_uri)

        if not request.state_token.strip() or not request.code_challenge.strip():
            raise CalendarOAuthError(
                "google_oauth_authorization_request_invalid",
                retryable=False,
            )

        parameters = {
            "access_type": "offline",
            "client_id": self._client_id,
            "code_challenge": request.code_challenge,
            "code_challenge_method": "S256",
            "include_granted_scopes": "true",
            "redirect_uri": request.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self._scopes),
            "state": request.state_token,
        }

        return (
            f"{_GOOGLE_AUTHORIZATION_ENDPOINT}?"
            f"{urlencode(parameters)}"
        )

    async def exchange_code(
        self,
        *,
        exchange: CalendarOAuthCodeExchange,
    ) -> ResolvedCalendarCredentials:
        """
        Exchange one authorization code without exposing provider details.

        A refresh token is mandatory because calendar synchronization continues
        after the browser session ends.
        """
        _validate_redirect_uri(exchange.redirect_uri)

        try:
            response = await self._http_client.post(
                _GOOGLE_TOKEN_ENDPOINT,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret.get_secret_value(),
                    "code": exchange.authorization_code.get_secret_value(),
                    "code_verifier": exchange.code_verifier.get_secret_value(),
                    "grant_type": "authorization_code",
                    "redirect_uri": exchange.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            raise CalendarOAuthError(
                "google_oauth_token_exchange_unavailable",
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise CalendarOAuthError(
                "google_oauth_token_exchange_failed",
                retryable=True,
            ) from error

        if response.is_error:
            raise CalendarOAuthError(
                "google_oauth_token_exchange_rejected",
                retryable=_is_retryable_http_status(response.status_code),
            )

        try:
            payload: object = response.json()
        except (JSONDecodeError, ValueError) as error:
            raise CalendarOAuthError(
                "google_oauth_token_response_invalid",
                retryable=False,
            ) from error

        if not isinstance(payload, dict):
            raise CalendarOAuthError(
                "google_oauth_token_response_invalid",
                retryable=False,
            )

        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        token_type = payload.get("token_type")
        expires_in = payload.get("expires_in")

        if (
            not isinstance(access_token, str)
            or not access_token
            or not isinstance(refresh_token, str)
            or not refresh_token
            or not isinstance(token_type, str)
            or token_type.lower() != "bearer"
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or not 1 <= expires_in <= _MAX_TOKEN_EXPIRY_SECONDS
        ):
            raise CalendarOAuthError(
                "google_oauth_token_response_invalid",
                retryable=False,
            )

        return ResolvedCalendarCredentials(
            values={
                "access_token": SecretStr(access_token),
                "expires_in_seconds": SecretStr(str(expires_in)),
                "refresh_token": SecretStr(refresh_token),
                "token_type": SecretStr("Bearer"),
            }
        )

    async def aclose(self) -> None:
        """Close the injected HTTP client during application shutdown."""
        await self._http_client.aclose()
