"""Long-running worker that expires due sent offers."""

import asyncio
import os
import socket
import time
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.services.offer_expiry import expire_due_offers

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Use configured identity or a process-specific operational identifier."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"offer-expiry:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker for the container health-check process."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def main() -> None:
    """Poll PostgreSQL and expire bounded batches of due offers."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the offer expiry worker."
        )

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.offer_expiry_worker_id)

    logger.info(
        "offer_expiry_worker_started",
        worker_id=worker_id,
        batch_size=settings.offer_expiry_worker_batch_size,
    )

    try:
        while True:
            cycle_started = time.monotonic()

            try:
                async with database.session_factory() as session:
                    result = await expire_due_offers(
                        session,
                        batch_size=settings.offer_expiry_worker_batch_size,
                        request_id=worker_id,
                    )

                _record_heartbeat(settings.offer_expiry_worker_heartbeat_path)

                logger.info(
                    "offer_expiry_worker_cycle_complete",
                    worker_id=worker_id,
                    expired_count=result.expired_count,
                    duration_seconds=round(
                        time.monotonic() - cycle_started,
                        3,
                    ),
                )

                if result.expired_count == 0:
                    await asyncio.sleep(
                        settings.offer_expiry_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "offer_expiry_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.offer_expiry_worker_poll_interval_seconds
                )
    finally:
        await database.dispose()
        logger.info("offer_expiry_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
