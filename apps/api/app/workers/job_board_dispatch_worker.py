"""Long-running worker for retry-safe job-board publication dispatch."""

import asyncio
import os
import socket
import time
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.job_boards.local_provider import LocalJobBoardProvider
from app.services.job_board_dispatch import dispatch_job_board_events
from app.services.job_board_provider import JobBoardProvider
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def worker_id(configured_worker_id: str | None) -> str:
    """Return a configured identity or a process-specific worker identifier."""
    if configured_worker_id is not None:
        return configured_worker_id
    return f"job-board-dispatch:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Refresh the liveness marker consumed by the container health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _build_providers(settings: Settings) -> Mapping[str, JobBoardProvider]:
    """Construct explicitly configured provider adapters; never guess a vendor."""
    if settings.job_board_provider == "none":
        raise RuntimeError(
            "JOB_BOARD_PROVIDER must be configured before the job-board "
            "dispatch worker can start."
        )
    if settings.job_board_provider == "local":
        if settings.app_env not in {"local", "test"}:
            raise RuntimeError(
                "The local job-board provider is permitted only in local and test environments."
            )
        provider = LocalJobBoardProvider()
        return {provider.provider_key: provider}
    raise RuntimeError("Unsupported job-board provider configuration.")


async def main() -> None:
    """Poll PostgreSQL and dispatch bounded batches of job-board events."""
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the job-board dispatch worker."
        )

    providers = _build_providers(settings)
    operational_worker_id = worker_id(settings.job_board_dispatch_worker_id)
    policy = OutboxWorkerPolicy(
        batch_size=settings.job_board_dispatch_worker_batch_size,
        visibility_timeout=timedelta(
            seconds=settings.job_board_dispatch_visibility_timeout_seconds
        ),
    )
    database = Database(str(settings.database_url))

    logger.info(
        "job_board_dispatch_worker_started",
        worker_id=operational_worker_id,
        providers=sorted(providers),
        batch_size=policy.batch_size,
    )

    try:
        while True:
            cycle_started = time.monotonic()
            try:
                async with database.session_factory() as session:
                    result = await dispatch_job_board_events(
                        session,
                        worker_id=operational_worker_id,
                        providers=providers,
                        policy=policy,
                    )

                _record_heartbeat(
                    settings.job_board_dispatch_worker_heartbeat_path
                )
                logger.info(
                    "job_board_dispatch_worker_cycle_complete",
                    worker_id=operational_worker_id,
                    claimed=result.claimed,
                    processed=result.processed,
                    retried=result.retried,
                    dead_lettered=result.dead_lettered,
                    duration_seconds=round(time.monotonic() - cycle_started, 3),
                )
                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.job_board_dispatch_worker_poll_interval_seconds
                    )
            except (OSError, RuntimeError, SQLAlchemyError, ValueError):
                logger.exception(
                    "job_board_dispatch_worker_cycle_failed",
                    worker_id=operational_worker_id,
                )
                await asyncio.sleep(
                    settings.job_board_dispatch_worker_poll_interval_seconds
                )
    finally:
        await database.dispose()
        logger.info(
            "job_board_dispatch_worker_stopped",
            worker_id=operational_worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
