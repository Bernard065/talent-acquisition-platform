"""Container health check for the document malware scan worker."""

import asyncio
import contextlib
import time

from app.core.config import get_settings
from app.db.session import Database


async def _ping_clamav(host: str, port: int, timeout_seconds: int) -> None:
    """Verify that the private ClamAV daemon can answer a PING request."""
    writer: asyncio.StreamWriter | None = None

    try:
        reader, connected_writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout_seconds,
        )
        writer = connected_writer
        connected_writer.write(b"zPING\0")
        await asyncio.wait_for(
            connected_writer.drain(),
            timeout=timeout_seconds,
        )

        response = await asyncio.wait_for(
            reader.readuntil(b"\0"),
            timeout=timeout_seconds,
        )
        if response.rstrip(b"\0") != b"PONG":
            raise RuntimeError("ClamAV returned an unexpected health response.")
    finally:
        if writer is not None:
            writer.close()
            with contextlib.suppress(ConnectionError):
                await writer.wait_closed()


async def main() -> None:
    """Fail unless worker liveness, PostgreSQL, and ClamAV are all healthy."""
    settings = get_settings()
    heartbeat_path = settings.scan_worker_heartbeat_path

    if not heartbeat_path.exists():
        raise RuntimeError("Worker heartbeat file does not exist.")

    heartbeat_age = time.time() - heartbeat_path.stat().st_mtime
    if heartbeat_age > settings.scan_worker_heartbeat_max_age_seconds:
        raise RuntimeError("Worker heartbeat is stale.")

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for worker health checks.")

    database = Database(str(settings.database_url))
    try:
        await database.ping()
        await _ping_clamav(
            settings.clamav_host,
            settings.clamav_port,
            settings.clamav_timeout_seconds,
        )
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
