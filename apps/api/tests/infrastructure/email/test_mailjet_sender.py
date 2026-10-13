"""Mocked HTTP tests for the privacy-safe Mailjet notification adapter."""

from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.infrastructure.email.mailjet_sender import MailjetEmailSender
from app.services.email_sender import EmailDeliveryError, EmailMessage

_API_KEY = "mailjet_public_key_not_for_logs"
_SECRET_KEY = "mailjet_private_key_not_for_logs"  # noqa: S105
_RECIPIENT = "candidate.private@example.test"
_BODY = "Private candidate workflow reference: application/secret-id."


def _message() -> EmailMessage:
    return EmailMessage(
        notification_id=uuid4(),
        idempotency_key="f" * 64,
        recipient_email=_RECIPIENT,
        subject="Talent Acquisition Platform notification",
        text_body=_BODY,
    )


def _sender(
    handler: httpx.MockTransport,
) -> tuple[MailjetEmailSender, httpx.AsyncClient]:
    client = httpx.AsyncClient(transport=handler)
    return (
        MailjetEmailSender(
            api_key=SecretStr(_API_KEY),
            secret_key=SecretStr(_SECRET_KEY),
            from_address="notifications@example.com",
            http_client=client,
        ),
        client,
    )


@pytest.mark.asyncio
async def test_sends_one_recipient_using_mailjet_basic_auth() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "Messages": [
                    {
                        "Status": "success",
                        "To": [{"MessageUUID": "mailjet-message-123"}],
                    }
                ]
            },
        )

    sender, client = _sender(httpx.MockTransport(respond))
    message = _message()
    try:
        message_id = await sender.send(message)
    finally:
        await client.aclose()

    assert message_id == "mailjet-message-123"
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url == "https://api.mailjet.com/v3.1/send"
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.headers.get("Idempotency-Key") is None
    assert request.read() == httpx.Request(
        "POST",
        "https://api.mailjet.com/v3.1/send",
        json={
            "Messages": [
                {
                    "From": {"Email": "notifications@example.com"},
                    "To": [{"Email": _RECIPIENT}],
                    "Subject": message.subject,
                    "TextPart": _BODY,
                }
            ]
        },
    ).read()


@pytest.mark.parametrize(
    ("status_code", "retryable", "expected_code"),
    [
        (400, False, "mailjet_provider_rejected"),
        (401, False, "mailjet_provider_rejected"),
        (403, False, "mailjet_provider_rejected"),
        (408, False, "mailjet_provider_rejected"),
        (429, True, "mailjet_rate_limited"),
        (500, False, "mailjet_provider_rejected"),
        (503, False, "mailjet_provider_rejected"),
    ],
)
@pytest.mark.asyncio
async def test_provider_errors_use_safe_codes_and_retry_only_rate_limits(
    status_code: int,
    retryable: bool,
    expected_code: str,
) -> None:
    private_text = f"Rejected {_RECIPIENT}; {_API_KEY}; {_SECRET_KEY}; {_BODY}"
    sender, client = _sender(
        httpx.MockTransport(
            lambda _: httpx.Response(status_code, json={"ErrorMessage": private_text})
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
    assert all(
        value not in str(raised.value)
        for value in (_RECIPIENT, _API_KEY, _SECRET_KEY, _BODY)
    )


@pytest.mark.asyncio
async def test_transport_failure_is_terminal_because_acceptance_is_ambiguous() -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private provider response")

    sender, client = _sender(httpx.MockTransport(fail))
    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == "mailjet_transport_outcome_unknown"
    assert raised.value.retryable is False
    assert "private provider response" not in str(raised.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"Messages": []},
        {"Messages": [{"Status": "error", "To": [{"MessageUUID": "id"}]}]},
        {"Messages": [{"Status": "success", "To": []}]},
        {"Messages": [{"Status": "success", "To": [{"MessageUUID": ""}]}]},
    ],
)
@pytest.mark.asyncio
async def test_malformed_success_response_is_terminal(payload: object) -> None:
    sender, client = _sender(
        httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    try:
        with pytest.raises(EmailDeliveryError) as raised:
            await sender.send(_message())
    finally:
        await client.aclose()

    assert raised.value.code == "mailjet_success_response_invalid"
    assert raised.value.retryable is False


def test_mailjet_does_not_advertise_provider_idempotency() -> None:
    assert MailjetEmailSender.idempotency_retry_window is None
