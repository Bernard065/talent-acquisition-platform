"""Long-running worker for signed outbound webhook delivery."""

from __future__ import annotations

import asyncio
import os
import socket
from pathlib import Path

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.infrastructure.webhooks import SignedWebhookDeliveryAdapter
from app.services.webhook_delivery import WebhookDeliveryPolicy
from app.services.webhook_delivery_worker import (
    process_pending_webhook_deliveries,
)

logger = structlog.get_logger()


def _worker_id(configured_worker_id: str | None) -> str:
    """Return a configured worker ID or a process-specific default."""
    if configured_worker_id is not None:
        return configured_worker_id

    return f"webhook-delivery:{socket.gethostname()}:{os.getpid()}"[:255]


def _record_heartbeat(path: Path) -> None:
    """Write a liveness marker used by the container health check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _require_setting(value: str | None, *, name: str) -> str:
    """Require startup configuration without exposing values."""
    if value is None:
        raise RuntimeError(f"{name} is required for the webhook worker.")

    return value


async def _build_dispatcher(
    settings: Settings,
) -> SignedWebhookDeliveryAdapter:
    """Build the vault-backed signed webhook adapter."""
    if settings.credential_vault_provider != "infisical":
        raise RuntimeError(
            "CREDENTIAL_VAULT_PROVIDER=infisical is required for webhook delivery."
        )

    if not settings.webhook_allowed_hosts:
        raise RuntimeError(
            "WEBHOOK_ALLOWED_HOSTS must contain at least one approved host."
        )

    infisical_client_secret = settings.infisical_client_secret
    if infisical_client_secret is None:
        raise RuntimeError(
            "INFISICAL_CLIENT_SECRET is required for webhook delivery."
        )

    vault = await InfisicalCredentialVault.from_universal_auth(
        project_id=_require_setting(
            settings.infisical_project_id,
            name="INFISICAL_PROJECT_ID",
        ),
        environment_slug=settings.infisical_environment,
        client_id=_require_setting(
            settings.infisical_client_id,
            name="INFISICAL_CLIENT_ID",
        ),
        client_secret=infisical_client_secret.get_secret_value(),
        host=str(settings.infisical_host),
    )

    return SignedWebhookDeliveryAdapter(
        signing_secret_vault=vault,
        allowed_hosts=settings.webhook_allowed_hosts,
        timeout_seconds=settings.webhook_delivery_timeout_seconds,
    )


async def main() -> None:
    """Poll and deliver queued webhook events."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError(
            "DATABASE_URL is required for the webhook delivery worker."
        )

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.webhook_delivery_worker_id)
    dispatcher: SignedWebhookDeliveryAdapter | None = None

    try:
        dispatcher = await _build_dispatcher(settings)
        policy = WebhookDeliveryPolicy(
            batch_size=settings.webhook_delivery_worker_batch_size,
        )

        logger.info(
            "webhook_delivery_worker_started",
            worker_id=worker_id,
            batch_size=settings.webhook_delivery_worker_batch_size,
        )

        while True:
            try:
                async with database.session_factory() as session:
                    result = await process_pending_webhook_deliveries(
                        session,
                        worker_id=worker_id,
                        dispatcher=dispatcher,
                        policy=policy,
                    )

                _record_heartbeat(
                    settings.webhook_delivery_worker_heartbeat_path
                )

                logger.info(
                    "webhook_delivery_worker_cycle_complete",
                    worker_id=worker_id,
                    claimed=result.claimed,
                    delivered=result.delivered,
                    retried=result.retried,
                    failed=result.failed,
                    disabled=result.disabled,
                )

                if result.claimed == 0:
                    await asyncio.sleep(
                        settings.webhook_delivery_worker_poll_interval_seconds
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                logger.error(
                    "webhook_delivery_worker_cycle_failed",
                    worker_id=worker_id,
                )
                await asyncio.sleep(
                    settings.webhook_delivery_worker_poll_interval_seconds
                )
    finally:
        if dispatcher is not None:
            await dispatcher.aclose()

        await database.dispose()
        logger.info(
            "webhook_delivery_worker_stopped",
            worker_id=worker_id,
        )


if __name__ == "__main__":
    asyncio.run(main())
