"""Long-running worker for durable offer-signature dispatch."""

import asyncio
import os
import socket
from collections.abc import Mapping
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.signatures.local_provider import LocalOfferSignatureProvider
from app.services.offer_signature_dispatch import (
    dispatch_offer_signature_requests,
)
from app.services.offer_signature_provider import OfferSignatureProvider
from app.services.outbox_worker import OutboxWorkerPolicy

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Return a configured worker identity or a process-specific default."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"offer-signature-dispatch:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker used by the container health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _build_providers(
    settings: Settings,
) -> Mapping[str, OfferSignatureProvider]:
    """
    Construct configured signature providers.

    The local adapter is intentionally prohibited in staging and production:
    it does not create a legally binding signature request or notify a
    candidate. Add a real provider adapter before enabling this worker there.
    """
    if settings.offer_signature_provider == "none":
        raise RuntimeError(
            "OFFER_SIGNATURE_PROVIDER must be configured for the "
            "offer signature dispatch worker."
        )

    if settings.offer_signature_provider == "local":
        if settings.app_env not in {"local", "test"}:
            raise RuntimeError(
                "The local offer-signature provider is permitted only in "
                "local and test environments."
            )

        provider = LocalOfferSignatureProvider()
        return {provider.provider: provider}

    raise RuntimeError("Unsupported offer signature provider.")


async def main() -> None:
    """Poll claimed outbox events and dispatch signature requests."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the offer signature dispatch worker."
        )

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.offer_signature_dispatch_worker_id)
    providers = _build_providers(settings)
    policy = OutboxWorkerPolicy(
        batch_size=settings.offer_signature_dispatch_worker_batch_size,
    )

    logger.info(
        "offer_signature_dispatch_worker_started",
        worker_id=worker_id,
        batch_size=settings.offer_signature_dispatch_worker_batch_size,
        providers=sorted(providers),
    )

    try:
        while True:
            try:
                async with database.session_factory() as session:
                    result = await dispatch_offer_signature_requests(
                        session,
                        worker_id=worker_id,
                        providers=providers,
                        policy=policy,
                    )

                _record_heartbeat(
                    settings.offer_signature_dispatch_worker_heartbeat_path
                )

                logger.info(
                    "offer_signature_dispatch_worker_cycle_complete",
                    worker_id=worker_id,
                    claimed=result.claimed,
                    processed=result.processed,
                    retried=result.retried,
                    dead_lettered=result.dead_lettered,
                )

                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.offer_signature_dispatch_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.exception(
                    "offer_signature_dispatch_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.offer_signature_dispatch_worker_poll_interval_seconds
                )
    finally:
        await database.dispose()
        logger.info(
            "offer_signature_dispatch_worker_stopped",
            worker_id=worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
