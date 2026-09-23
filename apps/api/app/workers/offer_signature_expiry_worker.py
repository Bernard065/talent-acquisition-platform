"""Long-running worker that expires due sent offer signature requests."""

import asyncio
import os
import socket
import time
from pathlib import Path

import structlog
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.services.offer_signature_expiry import (
    expire_due_offer_signature_requests,
)

logger = structlog.get_logger()


def worker_id(configured_worker_id: str | None) -> str:
    """Return configured identity or a process-specific worker identifier."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"offer-signature-expiry:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker consumed by the container health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def main() -> None:
    """Poll PostgreSQL and expire bounded batches of signature requests."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the offer signature expiry worker."
        )

    database = Database(str(settings.database_url))
    operational_worker_id = worker_id(
        settings.offer_signature_expiry_worker_id
    )

    logger.info(
        "offer_signature_expiry_worker_started",
        worker_id=operational_worker_id,
        batch_size=settings.offer_signature_expiry_worker_batch_size,
    )

    try:
        while True:
            cycle_started = time.monotonic()

            try:
                async with database.session_factory() as session:
                    result = await expire_due_offer_signature_requests(
                        session,
                        batch_size=(
                            settings.offer_signature_expiry_worker_batch_size
                        ),
                        request_id=operational_worker_id,
                    )

                _record_heartbeat(
                    settings.offer_signature_expiry_worker_heartbeat_path
                )

                logger.info(
                    "offer_signature_expiry_worker_cycle_complete",
                    worker_id=operational_worker_id,
                    expired_count=result.expired_count,
                    duration_seconds=round(
                        time.monotonic() - cycle_started,
                        3,
                    ),
                )

                if result.expired_count == 0:
                    await asyncio.sleep(
                        settings.offer_signature_expiry_worker_poll_interval_seconds
                    )
            except (OSError, RuntimeError, SQLAlchemyError, ValueError):
                logger.exception(
                    "offer_signature_expiry_worker_cycle_failed",
                    worker_id=operational_worker_id,
                )
                await asyncio.sleep(
                    settings.offer_signature_expiry_worker_poll_interval_seconds
                )
    finally:
        await database.dispose()
        logger.info(
            "offer_signature_expiry_worker_stopped",
            worker_id=operational_worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
