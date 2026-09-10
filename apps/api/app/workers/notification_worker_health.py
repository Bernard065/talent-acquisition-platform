"""Docker health check for the notification worker."""

import sys
import time

from app.core.config import get_settings


def main() -> None:
    """Exit successfully only when the worker heartbeat is fresh."""
    settings = get_settings()
    path = settings.notification_worker_heartbeat_path

    if not path.exists():
        sys.exit(1)

    age_seconds = time.time() - path.stat().st_mtime
    sys.exit(
        0
        if age_seconds <= settings.notification_worker_heartbeat_max_age_seconds
        else 1
    )


if __name__ == "__main__":
    main()
