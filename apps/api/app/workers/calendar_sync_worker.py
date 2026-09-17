"""Long-running worker for Google Calendar interview synchronization."""

import asyncio
import os
import socket
from collections.abc import Mapping
from pathlib import Path

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.domains.calendar.enums import CalendarProvider
from app.infrastructure.calendar.google_calendar_events import (
    GoogleCalendarEventProvider,
)
from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.services.calendar_provider import CalendarEventProvider
from app.services.calendar_sync_worker import (
    process_interview_calendar_sync_events,
)
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Return a configured worker identity or a process-specific default."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"calendar-sync:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker for the worker health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _require_setting(value: str | None, *, name: str) -> str:
    """Return a required startup setting without exposing its value."""
    if value is None:
        raise RuntimeError(f"{name} is required for the calendar sync worker.")

    return value


async def _build_google_runtime(
    settings: Settings,
) -> tuple[
    InfisicalCredentialVault,
    Mapping[CalendarProvider, CalendarEventProvider],
    httpx.AsyncClient,
]:
    """Build the credential resolver and Google event provider for this process."""
    if settings.calendar_oauth_provider != "google":
        raise RuntimeError(
            "CALENDAR_OAUTH_PROVIDER=google is required for the calendar sync worker."
        )

    if settings.credential_vault_provider != "infisical":
        raise RuntimeError(
            "CREDENTIAL_VAULT_PROVIDER=infisical is required for the "
            "calendar sync worker."
        )

    infisical_client_secret = settings.infisical_client_secret
    if infisical_client_secret is None:
        raise RuntimeError(
            "INFISICAL_CLIENT_SECRET is required for the calendar sync worker."
        )

    vault = await InfisicalCredentialVault.from_universal_auth(
        project_id=_require_setting(
            settings.infisical_project_id,
            name="INFISICAL_PROJECT_ID",
        ),
        environment_slug=settings.infisical_environment,
        client_id=_require_setting(
            settings.infisical_client_id,
            name="INFISICAL_CLIENT_ID",
        ),
        client_secret=infisical_client_secret.get_secret_value(),
        host=str(settings.infisical_host),
    )

    client_id_secret = await vault.read_runtime_secret(
        secret_name=_require_setting(
            settings.google_calendar_oauth_client_id_secret_name,
            name="GOOGLE_CALENDAR_OAUTH_CLIENT_ID_SECRET_NAME",
        )
    )
    client_secret = await vault.read_runtime_secret(
        secret_name=_require_setting(
            settings.google_calendar_oauth_client_secret_secret_name,
            name="GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET_SECRET_NAME",
        )
    )

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.calendar_oauth_http_connect_timeout_seconds,
            read=settings.calendar_oauth_http_read_timeout_seconds,
            write=settings.calendar_oauth_http_read_timeout_seconds,
            pool=settings.calendar_oauth_http_connect_timeout_seconds,
        ),
        follow_redirects=False,
    )

    try:
        providers: Mapping[CalendarProvider, CalendarEventProvider] = {
            CalendarProvider.GOOGLE: GoogleCalendarEventProvider(
                client_id=client_id_secret.get_secret_value(),
                client_secret=client_secret,
                http_client=http_client,
            ),
        }
    except Exception:
        await http_client.aclose()
        raise

    return vault, providers, http_client


async def main() -> None:
    """Poll calendar outbox events and synchronize Google Calendar records."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the calendar sync worker."
        )

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.calendar_sync_worker_id)
    http_client: httpx.AsyncClient | None = None

    try:
        credential_resolver, providers, http_client = await _build_google_runtime(
            settings
        )

        policy = OutboxWorkerPolicy(
            batch_size=settings.calendar_sync_worker_batch_size,
        )

        logger.info(
            "calendar_sync_worker_started",
            worker_id=worker_id,
            batch_size=settings.calendar_sync_worker_batch_size,
            provider=CalendarProvider.GOOGLE.value,
        )

        while True:
            try:
                async with database.session_factory() as session:
                    result = await process_interview_calendar_sync_events(
                        session,
                        worker_id=worker_id,
                        credential_resolver=credential_resolver,
                        providers=providers,
                        policy=policy,
                    )

                _record_heartbeat(
                    settings.calendar_sync_worker_heartbeat_path
                )

                logger.info(
                    "calendar_sync_worker_cycle_complete",
                    worker_id=worker_id,
                    claimed=result.claimed,
                    processed=result.processed,
                    retried=result.retried,
                    dead_lettered=result.dead_lettered,
                )

                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.calendar_sync_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "calendar_sync_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.calendar_sync_worker_poll_interval_seconds
                )
    finally:
        if http_client is not None:
            await http_client.aclose()

        await database.dispose()
        logger.info(
            "calendar_sync_worker_stopped",
            worker_id=worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
