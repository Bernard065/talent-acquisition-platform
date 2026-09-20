"""Long-running worker for durable BambooHR onboarding handoffs."""

from __future__ import annotations

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
from app.domains.hris.enums import HrisProvider
from app.infrastructure.hris.bamboohr_provider import BambooHrProviderAdapter
from app.infrastructure.hris.infisical_vault import InfisicalHrisCredentialVault
from app.services.hris_handoff_dispatch import dispatch_hris_handoff_events
from app.services.hris_provider import HrisProviderAdapter
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Return a configured worker identity or a process-specific default."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"hris-handoff:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker consumed by the Docker health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _require_setting(value: str | None, *, name: str) -> str:
    """Require startup configuration without exposing its value."""
    if value is None:
        raise RuntimeError(f"{name} is required for the HRIS handoff worker.")

    return value


async def _build_runtime(
    settings: Settings,
) -> tuple[
    InfisicalHrisCredentialVault,
    Mapping[HrisProvider, HrisProviderAdapter],
    httpx.AsyncClient,
]:
    """Build the external vault and explicitly configured HRIS provider."""
    if settings.hris_handoff_provider != "bamboohr":
        raise RuntimeError(
            "HRIS_HANDOFF_PROVIDER=bamboohr is required for this worker."
        )

    if settings.credential_vault_provider != "infisical":
        raise RuntimeError(
            "CREDENTIAL_VAULT_PROVIDER=infisical is required for HRIS handoffs."
        )

    infisical_client_secret = settings.infisical_client_secret
    if infisical_client_secret is None:
        raise RuntimeError(
            "INFISICAL_CLIENT_SECRET is required for the HRIS handoff worker."
        )

    vault = await InfisicalHrisCredentialVault.from_universal_auth(
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

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.hris_handoff_http_connect_timeout_seconds,
            read=settings.hris_handoff_http_read_timeout_seconds,
            write=settings.hris_handoff_http_read_timeout_seconds,
            pool=settings.hris_handoff_http_connect_timeout_seconds,
        ),
        follow_redirects=False,
    )

    providers: Mapping[HrisProvider, HrisProviderAdapter] = {
        HrisProvider.BAMBOOHR: BambooHrProviderAdapter(
            http_client=http_client,
        ),
    }

    return vault, providers, http_client


async def main() -> None:
    """Poll claimed outbox events and dispatch private BambooHR handoffs."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the HRIS handoff worker."
        )

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.hris_handoff_worker_id)
    http_client: httpx.AsyncClient | None = None

    try:
        credential_vault, providers, http_client = await _build_runtime(settings)
        policy = OutboxWorkerPolicy(
            batch_size=settings.hris_handoff_worker_batch_size,
        )

        logger.info(
            "hris_handoff_worker_started",
            worker_id=worker_id,
            batch_size=settings.hris_handoff_worker_batch_size,
            providers=sorted(provider.value for provider in providers),
        )

        while True:
            try:
                async with database.session_factory() as session:
                    result = await dispatch_hris_handoff_events(
                        session,
                        worker_id=worker_id,
                        credential_vault=credential_vault,
                        providers=providers,
                        policy=policy,
                    )

                _record_heartbeat(
                    settings.hris_handoff_worker_heartbeat_path
                )

                logger.info(
                    "hris_handoff_worker_cycle_complete",
                    worker_id=worker_id,
                    claimed=result.claimed,
                    processed=result.processed,
                    retried=result.retried,
                    dead_lettered=result.dead_lettered,
                )

                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.hris_handoff_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "hris_handoff_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.hris_handoff_worker_poll_interval_seconds
                )
    finally:
        if http_client is not None:
            await http_client.aclose()

        await database.dispose()

        logger.info(
            "hris_handoff_worker_stopped",
            worker_id=worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
