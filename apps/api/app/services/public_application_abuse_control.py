"""Safe construction of the public application abuse-control provider."""

from app.core.config import Settings
from app.infrastructure.abuse_control.local import LocalAllowAllAbuseGuard
from app.services.abuse_control import PublicApplicationAbuseGuard


def build_public_application_abuse_guard(
    settings: Settings,
) -> PublicApplicationAbuseGuard:
    """
    Build the configured abuse-control provider.

    A real CAPTCHA adapter is deliberately not faked. Production startup must
    fail until its provider credentials and verification implementation exist.
    """
    if settings.public_application_abuse_control_provider == "local_allow_all":
        if settings.app_env == "production":
            raise RuntimeError(
                "Production public applications require a CAPTCHA or "
                "rate-limit abuse-control provider."
            )
        return LocalAllowAllAbuseGuard()

    raise RuntimeError(
        "Configured public application abuse-control provider is unavailable."
    )
