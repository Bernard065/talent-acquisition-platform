"""Mocked HTTP tests for the privacy-safe, idempotent Resend adapter."""

from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.email.resend_sender import ResendEmailSender
from app.services.email_sender import EmailDeliveryError, EmailMessage

_API_KEY = "re_test_secret_do_not_log"
_RECIPIENT = "candidate.private@example.test"
_BODY = "Private candidate workflow reference: application/secret-id."


def _message(*, idempotency_key: str = "f" * 64) -> EmailMessage:
    """Return one notification payload without requiring a provider account."""
    return EmailMessage(
        notification_id=uuid4(),
        idempotency_key=idempotency_key,
        recipient_email=_RECIPIENT,
        subject="Talent Acquisition Platform notification",
        text_body=_BODY,
    )


def _sender(
    handler: httpx.MockTransport,
) -> tuple[ResendEmailSender, httpx.AsyncClient]:
    """Construct a sender with a request-capturing in-memory transport."""
    client = httpx.AsyncClient(transport=handler)
    return (
        ResendEmailSender(
            api_key=SecretStr(_API_KEY),
            from_address="notifications@example.com",
            http_client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_sends_stable_payload_with_bearer_and_idempotency_headers() -> None:
    """The provider receives stable retry parameters and no extra PII fields."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "provider-email-123"})

    sender, client = _sender(httpx.MockTransport(respond))
    message = _message()

    try:
        first_id = await sender.send(message)
        replay_id = await sender.send(message)
    finally:
        await client.aclose()

    assert first_id == replay_id == "provider-email-123"
    assert len(requests) == 2
    expected_payload = {
        "from": "notifications@example.com",
        "to": [_RECIPIENT],
        "subject": message.subject,
        "text": _BODY,
    }
    for request in requests:
        assert request.method == "POST"
        assert request.url == "https://api.resend.com/emails"
        assert request.headers["Authorization"] == f"Bearer {_API_KEY}"
        assert request.headers["Idempotency-Key"] == message.idempotency_key
        assert (
            request.read()
            == httpx.Request(
                "POST",
                "https://api.resend.com/emails",
                json=expected_payload,
            ).read()
        )


@pytest.mark.parametrize(
    ("status_code", "retryable", "expected_code"),
    [
        (400, False, "resend_request_rejected"),
        (401, False, "resend_request_rejected"),
        (408, True, "resend_provider_unavailable"),
        (429, True, "resend_rate_limited"),
        (500, True, "resend_provider_unavailable"),
        (503, True, "resend_provider_unavailable"),
        (302, False, "resend_request_rejected"),
    ],
)
@pytest.mark.asyncio
async def test_maps_provider_status_without_retaining_sensitive_response_text(
    status_code: int,
    retryable: bool,
    expected_code: str,
) -> None:
    """Only fixed safe error codes reach logs or the durable notification row."""
    private_response_text = f"Rejected {_RECIPIENT}; token={_API_KEY}; {_BODY}"
    sender, client = _sender(
        httpx.MockTransport(
            lambda _: httpx.Response(
                status_code,
                json={"message": private_response_text},
            )
        )
    )

    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == expected_code
    assert raised.value.retryable is retryable
    assert str(raised.value) == expected_code
    assert _RECIPIENT not in str(raised.value)
    assert _API_KEY not in str(raised.value)
    assert _BODY not in str(raised.value)


@pytest.mark.parametrize(
    ("provider_code", "retryable", "expected_code"),
    [
        (
            "concurrent_idempotent_requests",
            True,
            "resend_idempotent_request_in_progress",
        ),
        (
            "invalid_idempotent_request",
            False,
            "resend_idempotency_payload_conflict",
        ),
    ],
)
@pytest.mark.asyncio
async def test_classifies_idempotency_conflicts(
    provider_code: str,
    retryable: bool,
    expected_code: str,
) -> None:
    """Concurrent duplicate requests retry; payload mismatch is terminal."""
    sender, client = _sender(
        httpx.MockTransport(lambda _: httpx.Response(409, json={"name": provider_code}))
    )

    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == expected_code
    assert raised.value.retryable is retryable


@pytest.mark.asyncio
async def test_retries_transport_errors_with_same_provider_key() -> None:
    """A lost response is safely retryable because the provider key is stable."""

    def fail(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private detail")

    sender, client = _sender(httpx.MockTransport(fail))

    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == "resend_transport_error"
    assert raised.value.retryable is True
    assert "private detail" not in str(raised.value)


@pytest.mark.parametrize("response", [{}, {"id": ""}, {"id": "x" * 256}, ["bad"]])
@pytest.mark.asyncio
async def test_retries_malformed_success_response(response: object) -> None:
    """A possibly accepted request is retried only using the same key."""
    sender, client = _sender(httpx.MockTransport(lambda _: httpx.Response(200, json=response)))

    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == "resend_success_response_invalid"
    assert raised.value.retryable is True


@pytest.mark.asyncio
async def test_rejects_invalid_idempotency_key_before_network_request() -> None:
    """Provider key bounds are enforced locally before sending PII externally."""
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "provider-email-123"})

    sender, client = _sender(httpx.MockTransport(respond))

    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message(idempotency_key="k" * 257))
    finally:
        await client.aclose()

    assert raised.value.code == "resend_idempotency_key_invalid"
    assert raised.value.retryable is False
    assert requests == []


def test_sender_uses_a_retry_window_shorter_than_provider_retention() -> None:
    """The worker has a safety margin before Resend expires idempotency keys."""
    assert ResendEmailSender.idempotency_retry_window == timedelta(hours=23)
