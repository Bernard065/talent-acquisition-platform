"""Local and test abuse-control adapter."""

from app.services.abuse_control import PublicApplicationAbuseCheck


class LocalAllowAllAbuseGuard:
    """
    Explicit non-production adapter.

    It makes local development and isolated tests deterministic. Application
    startup must reject this adapter in production environments.
    """

    async def verify(self, check: PublicApplicationAbuseCheck) -> None:
        """Allow local/test traffic without persisting request metadata."""
        del check
