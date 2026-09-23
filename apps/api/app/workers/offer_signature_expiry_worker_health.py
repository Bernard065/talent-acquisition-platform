"""Container health check for the offer-signature expiry worker."""

import asyncio
import time

from app.core.config import get_settings
from app.db.session import Database


async def main() -> None:
    """Fail unless the worker heartbeat is fresh and PostgreSQL is reachable."""
    settings = get_settings()
    heartbeat_path = settings.offer_signature_expiry_worker_heartbeat_path

    if not heartbeat_path.exists():
        raise RuntimeError(
            "Offer signature expiry worker heartbeat file does not exist."
        )

    heartbeat_age = time.time() - heartbeat_path.stat().st_mtime
    if (
        heartbeat_age
        > settings.offer_signature_expiry_worker_heartbeat_max_age_seconds
    ):
        raise RuntimeError(
            "Offer signature expiry worker heartbeat is stale."
        )

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for offer signature expiry worker "
            "health checks."
        )

    database = Database(str(settings.database_url))
    try:
        await database.ping()
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
