"""Unit tests for the local offer-signature callback verifier."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import SecretStr

from app.infrastructure.signatures.local_callback_verifier import (
    LocalOfferSignatureCallbackVerifier,
)
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerificationRequest,
)
from app.services.offer_signature_errors import (
    OfferSignatureCallbackVerificationError,
)

_SIGNING_KEY = hashlib.sha256(
    b"local-callback-verifier-test-seed"
).hexdigest()[:32]
_NOW = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


def _body() -> bytes:
    """Return the strictly allowed local callback body."""
    return json.dumps(
        {
            "event_id": "event-123",
            "envelope_reference": "local-envelope-abc",
            "event_type": "signed",
            "occurred_at": "2026-09-21T09:59:00Z",
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _request(
    *,
    body: bytes | None = None,
    timestamp: int | None = None,
    signature: str | None = None,
) -> OfferSignatureCallbackVerificationRequest:
    """Create a correctly signed callback unless explicitly overridden."""
    raw_body = body or _body()
    unix_timestamp = timestamp or int(_NOW.timestamp())

    expected = hmac.new(
        _SIGNING_KEY.encode("utf-8"),
        f"{unix_timestamp}.".encode("ascii") + raw_body,
        hashlib.sha256,
    ).hexdigest()

    return OfferSignatureCallbackVerificationRequest(
        raw_body=raw_body,
        headers={
            "X-TAP-Timestamp": str(unix_timestamp),
            "X-TAP-Signature": signature or f"v1={expected}",
        },
        received_at=_NOW,
    )


def _verifier() -> LocalOfferSignatureCallbackVerifier:
    """Construct a deterministic verifier."""
    return LocalOfferSignatureCallbackVerifier(
        signing_secret=SecretStr(_SIGNING_KEY),
        clock=lambda: _NOW,
    )


@pytest.mark.asyncio
async def test_verifies_exact_signed_bytes_and_returns_safe_event() -> None:
    """A valid signed event yields only safe, normalized callback facts."""
    verified = await _verifier().verify(_request())

    assert verified.provider_event_id == "event-123"
    assert verified.provider_envelope_reference == "local-envelope-abc"
    assert verified.event_type.value == "signed"
    assert verified.occurred_at == datetime(2026, 9, 21, 9, 59, tzinfo=UTC)


@pytest.mark.asyncio
async def test_rejects_invalid_signature() -> None:
    """Changing the signature rejects the callback."""
    with pytest.raises(OfferSignatureCallbackVerificationError):
        await _verifier().verify(_request(signature="v1=not-valid"))


@pytest.mark.asyncio
async def test_rejects_body_mutation_after_signing() -> None:
    """The signature binds the exact raw body rather than parsed JSON."""
    original = _body()
    unix_timestamp = int(_NOW.timestamp())
    original_signature = hmac.new(
        _SIGNING_KEY.encode("utf-8"),
        f"{unix_timestamp}.".encode("ascii") + original,
        hashlib.sha256,
    ).hexdigest()
    request = OfferSignatureCallbackVerificationRequest(
        raw_body=(
            b'{"event_id":"event-123","envelope_reference":"changed",'
            b'"event_type":"signed","occurred_at":"2026-09-21T09:59:00Z"}'
        ),
        headers={
            "X-TAP-Timestamp": str(unix_timestamp),
            "X-TAP-Signature": f"v1={original_signature}",
        },
        received_at=_NOW,
    )

    with pytest.raises(OfferSignatureCallbackVerificationError):
        await _verifier().verify(request)


@pytest.mark.asyncio
async def test_rejects_stale_timestamp() -> None:
    """Callbacks outside the five-minute replay window are rejected."""
    stale = int((_NOW - timedelta(minutes=6)).timestamp())

    with pytest.raises(OfferSignatureCallbackVerificationError):
        await _verifier().verify(_request(timestamp=stale))


@pytest.mark.asyncio
async def test_rejects_unknown_or_sensitive_payload_fields() -> None:
    """The local event schema does not permit unreviewed provider fields."""
    payload = json.loads(_body())
    payload["signer_email"] = "private@example.test"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    with pytest.raises(OfferSignatureCallbackVerificationError):
        await _verifier().verify(_request(body=body))


@pytest.mark.asyncio
async def test_rejects_naive_event_timestamp() -> None:
    """Provider occurrence time must include a timezone offset."""
    payload = json.loads(_body())
    payload["occurred_at"] = "2026-09-21T09:59:00"
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    with pytest.raises(OfferSignatureCallbackVerificationError):
        await _verifier().verify(_request(body=body))
