"""Docker health check for the HRIS handoff worker."""

import sys
import time

from app.core.config import get_settings


def main() -> None:
    """Exit successfully only while the worker heartbeat remains fresh."""
    settings = get_settings()
    heartbeat_path = settings.hris_handoff_worker_heartbeat_path

    if not heartbeat_path.exists():
        sys.exit(1)

    heartbeat_age_seconds = time.time() - heartbeat_path.stat().st_mtime

    sys.exit(
        0
        if heartbeat_age_seconds
        <= settings.hris_handoff_worker_heartbeat_max_age_seconds
        else 1
    )


if __name__ == "__main__":
    main()
