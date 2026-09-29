"""Long-running worker that erases candidate records at configured processors."""

from __future__ import annotations

import asyncio
import os
import socket
import time
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

import httpx
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.domains.calendar.enums import CalendarProvider
from app.domains.hris.enums import HrisProvider
from app.infrastructure.hris.bamboohr_provider import BambooHrProviderAdapter
from app.infrastructure.processor_deletion.bamboohr import (
    BambooHrProcessorDeletionProvider,
)
from app.infrastructure.processor_deletion.google_calendar import (
    GoogleCalendarProcessorDeletionProvider,
)
from app.infrastructure.processor_deletion.local_signature import (
    LocalSignatureProcessorDeletionProvider,
)
from app.services.candidate_processor_deletion_dispatch import (
    CandidateProcessorDeletionPolicy,
    dispatch_candidate_processor_deletions,
)
from app.services.candidate_processor_provider import (
    CandidateProcessorDeletionProvider,
)

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    if configured_worker_id is not None:
        return configured_worker_id
    return f"processor-deletion:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def _build_runtime(
    settings: Settings,
) -> tuple[Mapping[str, CandidateProcessorDeletionProvider], list[httpx.AsyncClient]]:
    """Construct only explicitly configured provider adapters and resources."""
    providers: dict[str, CandidateProcessorDeletionProvider] = {}
    clients: list[httpx.AsyncClient] = []
    try:
        if settings.calendar_oauth_provider == "google":
            from app.workers.calendar_sync_worker import _build_google_runtime

            credential_resolver, calendar_providers, client = await _build_google_runtime(settings)
            clients.append(client)
            google_provider = calendar_providers.get(CalendarProvider.GOOGLE)
            if google_provider is None:
                raise RuntimeError("Google Calendar deletion provider could not be initialized.")
            providers["calendar.google"] = GoogleCalendarProcessorDeletionProvider(
                credential_resolver=credential_resolver,
                calendar_provider=google_provider,
            )

        if settings.hris_handoff_provider == "bamboohr":
            from app.workers.hris_handoff_worker import _build_runtime as _build_hris_runtime

            credential_vault, hris_providers, client = await _build_hris_runtime(settings)
            clients.append(client)
            bamboohr_provider = hris_providers.get(HrisProvider.BAMBOOHR)
            if not isinstance(bamboohr_provider, BambooHrProviderAdapter):
                raise RuntimeError("BambooHR deletion provider could not be initialized.")
            providers["hris.bamboohr"] = BambooHrProcessorDeletionProvider(
                credential_vault=credential_vault,
                bamboohr_provider=bamboohr_provider,
            )

        if settings.offer_signature_provider == "local":
            providers["signature.local"] = LocalSignatureProcessorDeletionProvider()

        if not providers:
            raise RuntimeError(
                "Configure at least one supported candidate processor before "
                "starting the processor deletion worker."
            )
        return providers, clients
    except Exception:
        for client in clients:
            await client.aclose()
        raise


async def main() -> None:
    """Poll PostgreSQL and dispatch bounded, retry-safe deletion batches."""
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.candidate_processor_deletion_worker_enabled:
        raise RuntimeError(
            "Processor deletion dispatch is disabled. Enable it only after "
            "backup expiry, restore tombstones, and the employee-record "
            "retention schedule have been reviewed and implemented."
        )
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for the processor deletion worker.")

    providers, clients = await _build_runtime(settings)
    database: Database | None = None
    worker_id = _worker_id(settings.candidate_processor_deletion_worker_id)
    policy = CandidateProcessorDeletionPolicy(
        batch_size=settings.candidate_processor_deletion_worker_batch_size,
        max_attempts=settings.candidate_processor_deletion_worker_max_attempts,
        lease_timeout=timedelta(seconds=settings.candidate_processor_deletion_worker_lease_seconds),
        base_retry_delay=timedelta(
            seconds=settings.candidate_processor_deletion_worker_retry_base_seconds
        ),
        maximum_retry_delay=timedelta(
            seconds=settings.candidate_processor_deletion_worker_retry_max_seconds
        ),
    )

    try:
        database = Database(str(settings.database_url))
        logger.info(
            "candidate_processor_deletion_worker_started",
            worker_id=worker_id,
            batch_size=policy.batch_size,
            processors=sorted(providers),
        )
        while True:
            cycle_started = time.monotonic()
            try:
                async with database.session_factory() as session:
                    result = await dispatch_candidate_processor_deletions(
                        session,
                        worker_id=worker_id,
                        providers=providers,
                        policy=policy,
                    )
                _record_heartbeat(settings.candidate_processor_deletion_worker_heartbeat_path)
                logger.info(
                    "candidate_processor_deletion_worker_cycle_complete",
                    worker_id=worker_id,
                    claimed=result.claimed,
                    completed=result.completed,
                    retried=result.retried,
                    exceptions=result.exceptions,
                    lease_lost=result.lease_lost,
                    duration_seconds=round(time.monotonic() - cycle_started, 3),
                )
                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.candidate_processor_deletion_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "candidate_processor_deletion_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.candidate_processor_deletion_worker_poll_interval_seconds
                )
    finally:
        for client in clients:
            await client.aclose()
        if database is not None:
            await database.dispose()
        logger.info(
            "candidate_processor_deletion_worker_stopped",
            worker_id=worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
