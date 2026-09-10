"""Long-running worker for notification intent creation and local delivery."""

import asyncio
import os
import socket
from pathlib import Path

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.email.logging_sender import LoggingEmailSender
from app.services.notification_delivery import (
    NotificationDeliveryPolicy,
    process_pending_notifications,
)
from app.services.notification_intents import process_notification_request_events
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    if configured_worker_id is not None:
        return configured_worker_id

    return f"notification:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


async def main() -> None:
    """Poll notification requests, persist intents, and deliver local email."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.app_env == "production":
        raise RuntimeError(
            "A production idempotent email provider adapter is required."
        )

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for the notification worker.")

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.notification_worker_id)
    sender = LoggingEmailSender()

    outbox_policy = OutboxWorkerPolicy(
        batch_size=settings.notification_worker_batch_size
    )
    delivery_policy = NotificationDeliveryPolicy(
        batch_size=settings.notification_worker_batch_size
    )

    logger.info("notification_worker_started", worker_id=worker_id)

    try:
        while True:
            try:
                async with database.session_factory() as session:
                    intent_result = await process_notification_request_events(
                        session,
                        worker_id=worker_id,
                        policy=outbox_policy,
                    )
                    delivered_count = await process_pending_notifications(
                        session,
                        worker_id=worker_id,
                        sender=sender,
                        policy=delivery_policy,
                    )

                _record_heartbeat(settings.notification_worker_heartbeat_path)

                logger.info(
                    "notification_worker_cycle_complete",
                    worker_id=worker_id,
                    intents_claimed=intent_result.claimed,
                    intents_processed=intent_result.processed,
                    intents_dead_lettered=intent_result.dead_lettered,
                    delivered_count=delivered_count,
                )

                if intent_result.claimed == 0 and delivered_count == 0:
                    await asyncio.sleep(
                        settings.notification_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "notification_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.notification_worker_poll_interval_seconds
                )
    finally:
        await database.dispose()
        logger.info("notification_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
