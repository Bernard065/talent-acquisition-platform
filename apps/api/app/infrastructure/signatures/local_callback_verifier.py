"""HMAC-verified local development callback adapter for offer signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from pydantic import SecretStr

from app.domains.signatures.enums import OfferSignatureCallbackEventType
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerificationRequest,
    VerifiedOfferSignatureCallback,
)
from app.services.offer_signature_errors import (
    OfferSignatureCallbackVerificationError,
)

_SIGNATURE_HEADER = "x-tap-signature"
_TIMESTAMP_HEADER = "x-tap-timestamp"
_MAX_CLOCK_SKEW = timedelta(minutes=5)
_MAX_EVENT_ID_LENGTH = 255
_MAX_ENVELOPE_REFERENCE_LENGTH = 255


def _utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


class LocalOfferSignatureCallbackVerifier:
    """
    Verify local development callbacks using an HMAC-SHA256 shared secret.

    The caller signs exact bytes with:

        HMAC_SHA256(secret, "<unix_timestamp>.<raw_body>")

    This adapter is intentionally for local/test use only. Production must use
    a provider-specific verifier that validates the provider's own signature
    scheme and event format.
    """

    provider = "local"

    def __init__(
        self,
        *,
        signing_secret: SecretStr,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not signing_secret.get_secret_value():
            raise ValueError("Local signature callback secret must not be empty.")

        self._signing_secret = signing_secret
        self._clock = clock

    async def verify(
        self,
        request: OfferSignatureCallbackVerificationRequest,
    ) -> VerifiedOfferSignatureCallback:
        """Verify the request signature, timestamp, and strict event schema."""
        timestamp = self._header(request.headers, _TIMESTAMP_HEADER)
        signature = self._header(request.headers, _SIGNATURE_HEADER)

        timestamp_value = self._parse_timestamp(timestamp)
        self._validate_timestamp(timestamp_value)

        expected_signature = self._expected_signature(
            timestamp=timestamp,
            raw_body=request.raw_body,
        )
        self._validate_signature(
            provided_signature=signature,
            expected_signature=expected_signature,
        )

        return self._parse_event(request.raw_body)

    @staticmethod
    def _header(headers: Mapping[str, str], name: str) -> str:
        """Read one required header without trusting its case."""
        value = next(
            (
                candidate_value
                for candidate_name, candidate_value in headers.items()
                if candidate_name.lower() == name
            ),
            None,
        )

        if value is None or not value.strip():
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_header_missing"
            )

        return value.strip()

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime:
        """Parse a Unix timestamp without accepting decimals or negatives."""
        try:
            epoch_seconds = int(timestamp)
        except ValueError as error:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_timestamp_invalid"
            ) from error

        if str(epoch_seconds) != timestamp or epoch_seconds < 0:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_timestamp_invalid"
            )

        return datetime.fromtimestamp(epoch_seconds, tz=UTC)

    def _validate_timestamp(self, timestamp: datetime) -> None:
        """Reject callbacks outside the bounded replay window."""
        now = self._clock().astimezone(UTC)

        if abs(now - timestamp) > _MAX_CLOCK_SKEW:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_timestamp_outside_replay_window"
            )

    def _expected_signature(self, *, timestamp: str, raw_body: bytes) -> str:
        """Create an HMAC over the exact inbound bytes."""
        payload = timestamp.encode("ascii") + b"." + raw_body

        digest = hmac.new(
            self._signing_secret.get_secret_value().encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return f"v1={digest}"

    @staticmethod
    def _validate_signature(
        *,
        provided_signature: str,
        expected_signature: str,
    ) -> None:
        """Use constant-time comparison to prevent timing leakage."""
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_signature_invalid"
            )

    @staticmethod
    def _parse_event(raw_body: bytes) -> VerifiedOfferSignatureCallback:
        """Parse a strict, privacy-safe local callback payload."""
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_payload_invalid"
            ) from error

        if not isinstance(payload, dict) or set(payload) != {
            "event_id",
            "envelope_reference",
            "event_type",
            "occurred_at",
        }:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_payload_invalid"
            )

        event_id = payload["event_id"]
        envelope_reference = payload["envelope_reference"]
        event_type = payload["event_type"]
        occurred_at = payload["occurred_at"]

        if (
            not isinstance(event_id, str)
            or not event_id.strip()
            or len(event_id) > _MAX_EVENT_ID_LENGTH
        ):
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_event_id_invalid"
            )

        if (
            not isinstance(envelope_reference, str)
            or not envelope_reference.strip()
            or len(envelope_reference) > _MAX_ENVELOPE_REFERENCE_LENGTH
        ):
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_envelope_reference_invalid"
            )

        if not isinstance(event_type, str):
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_event_type_invalid"
            )

        if not isinstance(occurred_at, str):
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_occurred_at_invalid"
            )

        try:
            parsed_event_type = OfferSignatureCallbackEventType(event_type)
            parsed_occurred_at = datetime.fromisoformat(
                occurred_at.replace("Z", "+00:00")
            )
        except ValueError as error:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_payload_invalid"
            ) from error

        if parsed_occurred_at.tzinfo is None:
            raise OfferSignatureCallbackVerificationError(
                "signature_callback_occurred_at_invalid"
            )

        return VerifiedOfferSignatureCallback(
            provider_event_id=event_id.strip(),
            provider_envelope_reference=envelope_reference.strip(),
            event_type=parsed_event_type,
            occurred_at=parsed_occurred_at.astimezone(UTC),
        )
