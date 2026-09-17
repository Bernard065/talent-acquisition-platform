"""Google Calendar event provider adapter."""

from base64 import b32hexencode
from datetime import datetime
from hashlib import sha256
from json import JSONDecodeError
from typing import Final, cast
from urllib.parse import quote

import httpx
from pydantic import SecretStr

from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_credentials import ResolvedCalendarCredentials
from app.services.calendar_provider import (
    CalendarEventDeletion,
    CalendarEventProvider,
    CalendarEventReference,
    CalendarEventUpsert,
    CalendarProviderError,
)

_GOOGLE_CALENDAR_API_BASE_URL: Final = "https://www.googleapis.com/calendar/v3"
_GOOGLE_TOKEN_URL: Final = "https://oauth2.googleapis.com/token"  # noqa: S105
_DEFAULT_CALENDAR_ID: Final = "primary"
_MAX_EXTERNAL_ID_LENGTH: Final = 500
_MAX_TITLE_LENGTH: Final = 256


def _is_retryable_status(status_code: int) -> bool:
    """Return whether a Google HTTP response is safe to retry."""
    return status_code in {408, 429} or 500 <= status_code <= 599


def _validate_interval(*, starts_at: datetime, ends_at: datetime) -> None:
    """Require a non-empty timezone-aware calendar interval."""
    if (
        starts_at.tzinfo is None
        or starts_at.utcoffset() is None
        or ends_at.tzinfo is None
        or ends_at.utcoffset() is None
        or ends_at <= starts_at
    ):
        raise CalendarProviderError(
            "invalid_calendar_event_interval",
            retryable=False,
        )


def _validate_event_title(title: str) -> None:
    """Limit this adapter to the approved privacy-safe event title."""
    if title != "Interview" or len(title) > _MAX_TITLE_LENGTH:
        raise CalendarProviderError(
            "invalid_calendar_event_title",
            retryable=False,
        )


def _calendar_id(external_calendar_id: str | None) -> str:
    """Return a bounded calendar identifier without interpreting its contents."""
    calendar_id = external_calendar_id or _DEFAULT_CALENDAR_ID

    if not calendar_id or len(calendar_id) > _MAX_EXTERNAL_ID_LENGTH:
        raise CalendarProviderError(
            "invalid_google_calendar_id",
            retryable=False,
        )

    return calendar_id


def _google_event_id(idempotency_key: str) -> str:
    """
    Build a stable Google-compatible event ID from an opaque UUID-like key.

    Google accepts lowercase base32hex characters. A deterministic ID makes a
    create retry safe even if the first provider response was lost.
    """
    if not idempotency_key or len(idempotency_key) > 255:
        raise CalendarProviderError(
            "invalid_calendar_idempotency_key",
            retryable=False,
        )

    encoded = b32hexencode(sha256(idempotency_key.encode("utf-8")).digest())
    return "tap" + encoded.decode("ascii").lower().rstrip("=")


def _event_path(*, calendar_id: str, event_id: str | None = None) -> str:
    """Build an encoded Google Calendar API event path."""
    encoded_calendar_id = quote(calendar_id, safe="")

    if event_id is None:
        return f"/calendars/{encoded_calendar_id}/events"

    if not event_id or len(event_id) > _MAX_EXTERNAL_ID_LENGTH:
        raise CalendarProviderError(
            "invalid_google_event_id",
            retryable=False,
        )

    return (
        f"/calendars/{encoded_calendar_id}/events/"
        f"{quote(event_id, safe='')}"
    )


def _event_payload(
    *,
    event: CalendarEventUpsert,
    include_event_id: bool,
) -> dict[str, object]:
    """Create the approved minimal event body without candidate PII."""
    _validate_interval(
        starts_at=event.starts_at,
        ends_at=event.ends_at,
    )
    _validate_event_title(event.title)

    payload: dict[str, object] = {
        "summary": event.title,
        "start": {"dateTime": event.starts_at.isoformat()},
        "end": {"dateTime": event.ends_at.isoformat()},
        "extendedProperties": {
            "private": {
                "tap_calendar_sync_key": event.idempotency_key,
            },
        },
    }

    if include_event_id:
        payload["id"] = _google_event_id(event.idempotency_key)

    return payload


def _response_mapping(response: httpx.Response) -> dict[str, object]:
    """Parse only the minimal JSON fields needed by this adapter."""
    try:
        payload = response.json()
    except (JSONDecodeError, ValueError) as error:
        raise CalendarProviderError(
            "google_calendar_invalid_response",
            retryable=False,
        ) from error

    if not isinstance(payload, dict):
        raise CalendarProviderError(
            "google_calendar_invalid_response",
            retryable=False,
        )

    return cast(dict[str, object], payload)


def _event_reference(response: httpx.Response) -> CalendarEventReference:
    """Extract a safe opaque Google event reference."""
    event_id = _response_mapping(response).get("id")

    if not isinstance(event_id, str) or not event_id:
        raise CalendarProviderError(
            "google_calendar_invalid_event_response",
            retryable=False,
        )

    return CalendarEventReference(external_event_id=event_id)


def _matches_idempotency_key(
    *,
    response: httpx.Response,
    idempotency_key: str,
) -> bool:
    """Verify a collision lookup belongs to this platform sync record."""
    payload = _response_mapping(response)
    properties = payload.get("extendedProperties")

    if not isinstance(properties, dict):
        return False

    private_properties = properties.get("private")
    if not isinstance(private_properties, dict):
        return False

    return private_properties.get("tap_calendar_sync_key") == idempotency_key


class GoogleCalendarEventProvider(CalendarEventProvider):
    """
    Google Calendar adapter for privacy-safe interview availability blocks.

    Refreshes an access token after a 401 and retries the original request
    exactly once. Refreshed access tokens stay in memory only; durable token
    rotation is intentionally a separate vault capability.
    """

    provider = CalendarProvider.GOOGLE

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        http_client: httpx.AsyncClient,
    ) -> None:
        """Construct the adapter from runtime-resolved client credentials."""
        if not client_id:
            raise ValueError("Google Calendar client ID is required.")

        self._client_id = client_id
        self._client_secret = client_secret
        self._http_client = http_client

    async def _send(
        self,
        *,
        method: str,
        path: str,
        access_token: SecretStr,
        json_body: dict[str, object] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send one authenticated Calendar API request without logging secrets."""
        try:
            return await self._http_client.request(
                method,
                f"{_GOOGLE_CALENDAR_API_BASE_URL}{path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": (
                        f"Bearer {access_token.get_secret_value()}"
                    ),
                },
                json=json_body,
                params=params,
            )
        except httpx.TimeoutException as error:
            raise CalendarProviderError(
                "google_calendar_timeout",
                retryable=True,
            ) from error
        except httpx.NetworkError as error:
            raise CalendarProviderError(
                "google_calendar_network_error",
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise CalendarProviderError(
                "google_calendar_http_error",
                retryable=True,
            ) from error

    async def _refresh_access_token(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
    ) -> SecretStr:
        """Exchange the stored refresh token for a short-lived access token."""
        refresh_token = credentials.required("refresh_token")

        try:
            response = await self._http_client.post(
                _GOOGLE_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret.get_secret_value(),
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token.get_secret_value(),
                },
            )
        except httpx.TimeoutException as error:
            raise CalendarProviderError(
                "google_calendar_refresh_timeout",
                retryable=True,
            ) from error
        except httpx.NetworkError as error:
            raise CalendarProviderError(
                "google_calendar_refresh_network_error",
                retryable=True,
            ) from error
        except httpx.HTTPError as error:
            raise CalendarProviderError(
                "google_calendar_refresh_http_error",
                retryable=True,
            ) from error

        if response.status_code < 200 or response.status_code >= 300:
            raise CalendarProviderError(
                "google_calendar_refresh_failed",
                retryable=_is_retryable_status(response.status_code),
            )

        access_token = _response_mapping(response).get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise CalendarProviderError(
                "google_calendar_refresh_invalid_response",
                retryable=False,
            )

        return SecretStr(access_token)

    async def _authorized_request(
        self,
        *,
        method: str,
        path: str,
        credentials: ResolvedCalendarCredentials,
        json_body: dict[str, object] | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request and refresh once only when Google rejects the token."""
        access_token = credentials.required("access_token")
        response = await self._send(
            method=method,
            path=path,
            access_token=access_token,
            json_body=json_body,
            params=params,
        )

        if response.status_code != 401:
            return response

        refreshed_access_token = await self._refresh_access_token(
            credentials=credentials,
        )
        return await self._send(
            method=method,
            path=path,
            access_token=refreshed_access_token,
            json_body=json_body,
            params=params,
        )

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        """Classify a Calendar API response without retaining provider details."""
        if 200 <= response.status_code < 300:
            return

        raise CalendarProviderError(
            "google_calendar_request_failed",
            retryable=_is_retryable_status(response.status_code),
        )

    async def upsert_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventUpsert,
    ) -> CalendarEventReference:
        """Create or update a minimal interview event without attendee data."""
        calendar_id = _calendar_id(event.external_calendar_id)
        params = {"sendUpdates": "none"}

        if event.external_event_id is not None:
            response = await self._authorized_request(
                method="PATCH",
                path=_event_path(
                    calendar_id=calendar_id,
                    event_id=event.external_event_id,
                ),
                credentials=credentials,
                json_body=_event_payload(
                    event=event,
                    include_event_id=False,
                ),
                params=params,
            )
            self._require_success(response)
            return _event_reference(response)

        deterministic_event_id = _google_event_id(event.idempotency_key)
        response = await self._authorized_request(
            method="POST",
            path=_event_path(calendar_id=calendar_id),
            credentials=credentials,
            json_body=_event_payload(
                event=event,
                include_event_id=True,
            ),
            params=params,
        )

        if response.status_code != 409:
            self._require_success(response)
            return _event_reference(response)

        # A previous create may have succeeded while its response was lost.
        existing = await self._authorized_request(
            method="GET",
            path=_event_path(
                calendar_id=calendar_id,
                event_id=deterministic_event_id,
            ),
            credentials=credentials,
        )

        if existing.status_code == 404:
            raise CalendarProviderError(
                "google_calendar_create_conflict_pending",
                retryable=True,
            )

        self._require_success(existing)

        if not _matches_idempotency_key(
            response=existing,
            idempotency_key=event.idempotency_key,
        ):
            raise CalendarProviderError(
                "google_calendar_idempotency_conflict",
                retryable=False,
            )

        return _event_reference(existing)

    async def delete_event(
        self,
        *,
        credentials: ResolvedCalendarCredentials,
        event: CalendarEventDeletion,
    ) -> None:
        """Delete an event idempotently without sending guest notifications."""
        calendar_id = _calendar_id(event.external_calendar_id)
        response = await self._authorized_request(
            method="DELETE",
            path=_event_path(
                calendar_id=calendar_id,
                event_id=event.external_event_id,
            ),
            credentials=credentials,
            params={"sendUpdates": "none"},
        )

        # A missing event means the desired deleted state has already been met.
        if response.status_code == 404:
            return

        self._require_success(response)
