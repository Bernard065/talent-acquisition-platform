"""Construct the configured public-application abuse-control provider."""

import httpx
from pydantic import SecretStr

from app.core.config import Settings
from app.infrastructure.abuse_control.cloudflare_turnstile import (
    CloudflareTurnstileAbuseGuard,
)
from app.infrastructure.abuse_control.local import LocalAllowAllAbuseGuard
from app.services.abuse_control import PublicApplicationAbuseGuard


def build_public_application_abuse_guard(
    settings: Settings,
    *,
    captcha_secret_key: SecretStr | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> PublicApplicationAbuseGuard:
    """Build the selected adapter; production must never use allow-all."""
    if settings.public_application_abuse_control_provider == "local_allow_all":
        if settings.app_env == "production":
            raise RuntimeError(
                "Production public applications require CAPTCHA verification."
            )
        return LocalAllowAllAbuseGuard()

    if settings.public_application_abuse_control_provider == "captcha":
        if captcha_secret_key is None or http_client is None:
            raise RuntimeError("CAPTCHA runtime dependencies are unavailable.")

        return CloudflareTurnstileAbuseGuard(
            secret_key=captcha_secret_key,
            expected_hostnames=frozenset(
                settings.public_application_captcha_expected_hostnames
            ),
            expected_action=settings.public_application_captcha_expected_action,
            http_client=http_client,
        )

    raise RuntimeError("Configured abuse-control provider is unavailable.")
