"""Unit tests for the Google Calendar event provider adapter."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from json import loads
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.calendar.google_calendar_events import (
    GoogleCalendarEventProvider,
)
from app.services.calendar_credentials import ResolvedCalendarCredentials
from app.services.calendar_provider import (
    CalendarEventDeletion,
    CalendarEventUpsert,
    CalendarProviderError,
)


def _credentials() -> ResolvedCalendarCredentials:
    """Create credentials held only in test process memory."""
    return ResolvedCalendarCredentials(
        values={
            "access_token": SecretStr("initial-access-token"),
            "refresh_token": SecretStr("refresh-token"),
        }
    )


def _upsert_event(
    *,
    external_event_id: str | None = None,
) -> CalendarEventUpsert:
    """Create a privacy-safe event command."""
    starts_at = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

    return CalendarEventUpsert(
        calendar_connection_id=uuid4(),
        interview_session_id=uuid4(),
        external_calendar_id=None,
        external_event_id=external_event_id,
        idempotency_key="b0c63795-1d3b-49c1-8e4c-46f83c37a5f6",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=45),
    )


def _deletion_event() -> CalendarEventDeletion:
    """Create a safe event deletion command."""
    return CalendarEventDeletion(
        calendar_connection_id=uuid4(),
        interview_session_id=uuid4(),
        external_calendar_id=None,
        external_event_id="google-event-id",
        idempotency_key="b0c63795-1d3b-49c1-8e4c-46f83c37a5f6",
    )


def _make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[GoogleCalendarEventProvider, httpx.AsyncClient]:
    """Build an adapter backed by an in-memory HTTP transport."""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = GoogleCalendarEventProvider(
        client_id="google-client-id",
        client_secret=SecretStr("google-client-secret"),
        http_client=client,
    )
    return provider, client


@pytest.mark.asyncio
async def test_creates_minimal_private_event_with_stable_google_id() -> None:
    """Create requests contain no candidate, attendee, or interview-content data."""
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            status_code=200,
            json={"id": "created-google-event-id"},
        )

    provider, client = _make_provider(handler)

    try:
        result = await provider.upsert_event(
            credentials=_credentials(),
            event=_upsert_event(),
        )
    finally:
        await client.aclose()

    assert captured_request is not None
    assert captured_request.method == "POST"
    assert captured_request.url.path == "/calendar/v3/calendars/primary/events"
    assert captured_request.url.params["sendUpdates"] == "none"
    assert captured_request.headers["Authorization"] == "Bearer initial-access-token"

    payload = loads(captured_request.content)
    assert payload["summary"] == "Interview"
    assert payload["start"] == {"dateTime": "2026-09-20T10:00:00+00:00"}
    assert payload["end"] == {"dateTime": "2026-09-20T10:45:00+00:00"}
    assert payload["extendedProperties"] == {
        "private": {
            "tap_calendar_sync_key": "b0c63795-1d3b-49c1-8e4c-46f83c37a5f6",
        },
    }

    event_id = payload["id"]
    assert isinstance(event_id, str)
    assert event_id.startswith("tap")
    assert all(character in "abcdefghijklmnopqrstuv0123456789" for character in event_id)

    serialized_payload = str(payload).lower()
    assert "candidate" not in serialized_payload
    assert "attendee" not in serialized_payload
    assert "email" not in serialized_payload
    assert "description" not in serialized_payload
    assert result.external_event_id == "created-google-event-id"


@pytest.mark.asyncio
async def test_updates_existing_event_without_replacing_its_id() -> None:
    """Existing provider events are updated through PATCH."""
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request

        return httpx.Response(
            status_code=200,
            json={"id": "existing-google-event-id"},
        )

    provider, client = _make_provider(handler)

    try:
        result = await provider.upsert_event(
            credentials=_credentials(),
            event=_upsert_event(
                external_event_id="existing-google-event-id",
            ),
        )
    finally:
        await client.aclose()

    assert captured_request is not None
    assert captured_request.method == "PATCH"
    assert (
        captured_request.url.path
        == "/calendar/v3/calendars/primary/events/existing-google-event-id"
    )

    payload = loads(captured_request.content)
    assert "id" not in payload
    assert result.external_event_id == "existing-google-event-id"


@pytest.mark.asyncio
async def test_create_conflict_recovers_matching_prior_create() -> None:
    """A lost create response is recovered through a deterministic event lookup."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.method == "POST":
            return httpx.Response(status_code=409)

        assert request.method == "GET"
        return httpx.Response(
            status_code=200,
            json={
                "id": "recovered-google-event-id",
                "extendedProperties": {
                    "private": {
                        "tap_calendar_sync_key": (
                            "b0c63795-1d3b-49c1-8e4c-46f83c37a5f6"
                        ),
                    },
                },
            },
        )

    provider, client = _make_provider(handler)

    try:
        result = await provider.upsert_event(
            credentials=_credentials(),
            event=_upsert_event(),
        )
    finally:
        await client.aclose()

    assert [request.method for request in requests] == ["POST", "GET"]
    assert result.external_event_id == "recovered-google-event-id"


@pytest.mark.asyncio
async def test_create_conflict_rejects_unrelated_existing_event() -> None:
    """A collision may never overwrite an event that this platform does not own."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(status_code=409)

        return httpx.Response(
            status_code=200,
            json={
                "id": "unrelated-google-event-id",
                "extendedProperties": {
                    "private": {
                        "tap_calendar_sync_key": "different-sync-key",
                    },
                },
            },
        )

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarProviderError) as error:
            await provider.upsert_event(
                credentials=_credentials(),
                event=_upsert_event(),
            )
    finally:
        await client.aclose()

    assert error.value.code == "google_calendar_idempotency_conflict"
    assert error.value.retryable is False


@pytest.mark.asyncio
async def test_refreshes_once_after_google_rejects_access_token() -> None:
    """A 401 triggers exactly one refresh and one retry of the original request."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        if request.url.path == "/calendar/v3/calendars/primary/events":
            if len(
                [
                    item
                    for item in requests
                    if item.url.path == "/calendar/v3/calendars/primary/events"
                ]
            ) == 1:
                assert request.headers["Authorization"] == "Bearer initial-access-token"
                return httpx.Response(status_code=401)

            assert request.headers["Authorization"] == "Bearer refreshed-access-token"
            return httpx.Response(
                status_code=200,
                json={"id": "created-after-refresh"},
            )

        assert request.url.path == "/token"
        submitted = parse_qs(request.content.decode("utf-8"))
        assert submitted["grant_type"] == ["refresh_token"]
        assert submitted["client_id"] == ["google-client-id"]
        assert submitted["client_secret"] == ["google-client-secret"]
        assert submitted["refresh_token"] == ["refresh-token"]

        return httpx.Response(
            status_code=200,
            json={"access_token": "refreshed-access-token"},
        )

    provider, client = _make_provider(handler)

    try:
        result = await provider.upsert_event(
            credentials=_credentials(),
            event=_upsert_event(),
        )
    finally:
        await client.aclose()

    assert result.external_event_id == "created-after-refresh"
    assert [request.url.path for request in requests] == [
        "/calendar/v3/calendars/primary/events",
        "/token",
        "/calendar/v3/calendars/primary/events",
    ]


@pytest.mark.asyncio
async def test_classifies_google_api_failures() -> None:
    """Retry only responses that are transient at the provider boundary."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(status_code=429)

        return httpx.Response(status_code=400)

    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarProviderError) as create_error:
            await provider.upsert_event(
                credentials=_credentials(),
                event=_upsert_event(),
            )

        with pytest.raises(CalendarProviderError) as delete_error:
            await provider.delete_event(
                credentials=_credentials(),
                event=_deletion_event(),
            )
    finally:
        await client.aclose()

    assert create_error.value.code == "google_calendar_request_failed"
    assert create_error.value.retryable is False
    assert delete_error.value.code == "google_calendar_request_failed"
    assert delete_error.value.retryable is True


@pytest.mark.asyncio
async def test_treats_missing_event_deletion_as_success() -> None:
    """Deleting an already removed provider event is idempotent."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return httpx.Response(status_code=404)

    provider, client = _make_provider(handler)

    try:
        await provider.delete_event(
            credentials=_credentials(),
            event=_deletion_event(),
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rejects_invalid_intervals_before_making_http_request() -> None:
    """Malformed event times fail locally and do not contact Google."""
    call_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(status_code=500)

    starts_at = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    invalid_event = CalendarEventUpsert(
        calendar_connection_id=uuid4(),
        interview_session_id=uuid4(),
        external_calendar_id=None,
        external_event_id=None,
        idempotency_key="b0c63795-1d3b-49c1-8e4c-46f83c37a5f6",
        starts_at=starts_at,
        ends_at=starts_at,
    )
    provider, client = _make_provider(handler)

    try:
        with pytest.raises(CalendarProviderError) as error:
            await provider.upsert_event(
                credentials=_credentials(),
                event=invalid_event,
            )
    finally:
        await client.aclose()

    assert error.value.code == "invalid_calendar_event_interval"
    assert error.value.retryable is False
    assert call_count == 0
