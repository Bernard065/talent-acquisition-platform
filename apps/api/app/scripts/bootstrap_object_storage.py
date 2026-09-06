"""Create the local MinIO document bucket explicitly."""

import asyncio

from app.core.config import get_settings
from app.infrastructure.object_storage.s3 import S3ObjectStorage


async def main() -> None:
    """Bootstrap object storage only for local development."""
    settings = get_settings()

    if settings.app_env != "local":
        raise RuntimeError(
            "Object-storage bootstrap is intentionally limited to APP_ENV=local."
        )

    storage = S3ObjectStorage.from_settings(settings)
    await storage.ensure_bucket()
    print(f"Object-storage bucket '{storage.config.bucket}' is ready.")


if __name__ == "__main__":
    asyncio.run(main())
