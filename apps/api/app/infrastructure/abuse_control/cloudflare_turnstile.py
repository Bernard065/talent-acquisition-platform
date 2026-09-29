"""Cloudflare Turnstile server-side abuse verification."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import SecretStr

from app.services.abuse_control import (
    AbuseControlRejectedError,
    AbuseControlUnavailableError,
    PublicApplicationAbuseCheck,
)

_SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

_REJECTED_CODES = frozenset(
    {
        "missing-input-response",
        "invalid-input-response",
        "timeout-or-duplicate",
    }
)
_CONFIGURATION_OR_PROVIDER_CODES = frozenset(
    {
        "bad-request",
        "internal-error",
        "missing-input-secret",
        "invalid-input-secret",
    }
)


@dataclass(slots=True)
class CloudflareTurnstileAbuseGuard:
    """Verify public application challenges without retaining request data."""

    secret_key: SecretStr
    expected_hostnames: frozenset[str]
    expected_action: str
    http_client: httpx.AsyncClient

    def __post_init__(self) -> None:
        self.expected_hostnames = frozenset(
            hostname.strip().rstrip(".").casefold()
            for hostname in self.expected_hostnames
        )
        if not self.expected_hostnames or not self.expected_action:
            raise ValueError("Turnstile hostname and action expectations are required.")

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Reject invalid challenges; fail closed if verification is unavailable."""
        token = check.challenge_token
        if not token or len(token) > 2_048:
            raise AbuseControlRejectedError("captcha_rejected")

        # Stable across retries of the same API write, but distinct for another
        # job or Idempotency-Key. Only the derived UUID is sent to Cloudflare.
        provider_idempotency_key = uuid5(
            NAMESPACE_URL,
            f"tap-public-application:{check.public_job_id}:{check.idempotency_key}",
        )

        try:
            response = await self.http_client.post(
                _SITEVERIFY_URL,
                data={
                    "secret": self.secret_key.get_secret_value(),
                    "response": token,
                    "idempotency_key": str(provider_idempotency_key),
                },
            )
        except httpx.RequestError:
            raise AbuseControlUnavailableError(
                "captcha_verification_unavailable"
            ) from None

        if response.status_code != httpx.codes.OK:
            raise AbuseControlUnavailableError(
                "captcha_verification_unavailable"
            )

        try:
            body: object = response.json()
        except ValueError:
            raise AbuseControlUnavailableError(
                "captcha_provider_invalid_response"
            ) from None

        if not isinstance(body, dict):
            raise AbuseControlUnavailableError(
                "captcha_provider_invalid_response"
            )

        success = body.get("success")
        if not isinstance(success, bool):
            raise AbuseControlUnavailableError(
                "captcha_provider_invalid_response"
            )

        if not success:
            raw_codes = body.get("error-codes", [])
            if not isinstance(raw_codes, list) or any(
                not isinstance(code, str) for code in raw_codes
            ):
                raise AbuseControlUnavailableError(
                    "captcha_provider_invalid_response"
                )

            codes = frozenset(raw_codes)
            if codes and codes <= _REJECTED_CODES:
                raise AbuseControlRejectedError("captcha_rejected")
            if codes & _CONFIGURATION_OR_PROVIDER_CODES:
                raise AbuseControlUnavailableError(
                    "captcha_verification_unavailable"
                )

            # Unknown provider errors fail closed; do not expose provider details.
            raise AbuseControlUnavailableError(
                "captcha_verification_unavailable"
            )

        hostname = body.get("hostname")
        action = body.get("action")
        if not isinstance(hostname, str) or not isinstance(action, str):
            raise AbuseControlUnavailableError(
                "captcha_provider_invalid_response"
            )

        if (
            hostname.strip().rstrip(".").casefold() not in self.expected_hostnames
            or action != self.expected_action
        ):
            raise AbuseControlRejectedError("captcha_rejected")
