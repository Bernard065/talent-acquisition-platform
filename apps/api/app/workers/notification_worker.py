"""Long-running worker for notification intent creation and email delivery."""

import asyncio
import os
import socket
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import structlog
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database
from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.infrastructure.email.logging_sender import LoggingEmailSender
from app.infrastructure.email.mailjet_sender import MailjetEmailSender
from app.infrastructure.email.resend_sender import ResendEmailSender
from app.services.email_sender import EmailSender
from app.services.notification_action_item_digests import (
    enqueue_action_item_digests,
)
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


def _require_setting(
    value: str | None,
    *,
    name: str,
    provider: str = "Resend",
) -> str:
    """Require runtime configuration without including secret values in errors."""
    if value is None:
        raise RuntimeError(f"{name} is required for {provider} email delivery.")
    return value


async def _build_sender(
    settings: Settings,
) -> tuple[EmailSender, httpx.AsyncClient | None]:
    """Construct the configured sender and return any worker-owned HTTP client."""
    if settings.notification_email_provider == "logging":
        if settings.app_env == "production":
            raise RuntimeError(
                "NOTIFICATION_EMAIL_PROVIDER=resend is required in production."
            )
        return LoggingEmailSender(), None

    if settings.notification_email_provider == "mailjet":
        from_address = settings.notification_email_from_address
        if from_address is None:
            raise RuntimeError(
                "NOTIFICATION_EMAIL_FROM_ADDRESS is required for Mailjet email delivery."
            )

        mailjet_api_key: SecretStr | None = None
        mailjet_secret_key: SecretStr | None = None
        if settings.credential_vault_provider == "infisical":
            client_secret = settings.infisical_client_secret
            if client_secret is None:
                raise RuntimeError(
                    "INFISICAL_CLIENT_SECRET is required for Mailjet email delivery."
                )

            api_key_secret_name = _require_setting(
                settings.notification_email_api_key_secret_name,
                name="NOTIFICATION_EMAIL_API_KEY_SECRET_NAME",
                provider="Mailjet",
            )
            secret_key_secret_name = _require_setting(
                settings.notification_email_secret_key_secret_name,
                name="NOTIFICATION_EMAIL_SECRET_KEY_SECRET_NAME",
                provider="Mailjet",
            )
            try:
                vault = await InfisicalCredentialVault.from_universal_auth(
                    project_id=_require_setting(
                        settings.infisical_project_id,
                        name="INFISICAL_PROJECT_ID",
                        provider="Mailjet",
                    ),
                    environment_slug=settings.infisical_environment,
                    client_id=_require_setting(
                        settings.infisical_client_id,
                        name="INFISICAL_CLIENT_ID",
                        provider="Mailjet",
                    ),
                    client_secret=client_secret.get_secret_value(),
                    host=str(settings.infisical_host),
                )
                mailjet_api_key = await vault.read_runtime_secret(
                    secret_name=api_key_secret_name,
                )
                mailjet_secret_key = await vault.read_runtime_secret(
                    secret_name=secret_key_secret_name,
                )
            except Exception as error:  # pylint: disable=broad-exception-caught
                logger.error(
                    "notification_email_credentials_unavailable",
                    error_type=type(error).__name__,
                )
                raise RuntimeError(
                    "Unable to initialize Mailjet credentials from Infisical."
                ) from None
        else:
            if settings.app_env not in {"local", "test"}:
                raise RuntimeError(
                    "CREDENTIAL_VAULT_PROVIDER=infisical is required for "
                    "Mailjet delivery outside local and test environments."
                )
            mailjet_api_key = settings.mailjet_api_key
            mailjet_secret_key = settings.mailjet_secret_key

        if mailjet_api_key is None or mailjet_secret_key is None:
            raise RuntimeError(
                "Mailjet API credentials are required for email delivery."
            )

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.notification_email_connect_timeout_seconds,
                read=settings.notification_email_read_timeout_seconds,
                write=settings.notification_email_read_timeout_seconds,
                pool=settings.notification_email_connect_timeout_seconds,
            ),
            follow_redirects=False,
        )
        return (
            MailjetEmailSender(
                api_key=mailjet_api_key,
                secret_key=mailjet_secret_key,
                from_address=str(from_address),
                http_client=http_client,
            ),
            http_client,
        )

    if settings.notification_email_provider != "resend":
        raise RuntimeError("A supported notification email provider is required.")

    if settings.credential_vault_provider != "infisical":
        raise RuntimeError(
            "CREDENTIAL_VAULT_PROVIDER=infisical is required for Resend delivery."
        )

    client_secret = settings.infisical_client_secret
    if client_secret is None:
        raise RuntimeError(
            "INFISICAL_CLIENT_SECRET is required for Resend email delivery."
        )

    secret_name = _require_setting(
        settings.notification_email_api_key_secret_name,
        name="NOTIFICATION_EMAIL_API_KEY_SECRET_NAME",
    )
    from_address = settings.notification_email_from_address
    if from_address is None:
        raise RuntimeError(
            "NOTIFICATION_EMAIL_FROM_ADDRESS is required for Resend email delivery."
        )

    try:
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
            client_secret=client_secret.get_secret_value(),
            host=str(settings.infisical_host),
        )
        resend_api_key: SecretStr = await vault.read_runtime_secret(
            secret_name=secret_name,
        )
    except Exception as error:  # pylint: disable=broad-exception-caught
        logger.error(
            "notification_email_credentials_unavailable",
            error_type=type(error).__name__,
        )
        raise RuntimeError(
            "Unable to initialize Resend credentials from Infisical."
        ) from None

    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.notification_email_connect_timeout_seconds,
            read=settings.notification_email_read_timeout_seconds,
            write=settings.notification_email_read_timeout_seconds,
            pool=settings.notification_email_connect_timeout_seconds,
        ),
        follow_redirects=False,
    )
    return (
        ResendEmailSender(
            api_key=resend_api_key,
            from_address=str(from_address),
            http_client=http_client,
        ),
        http_client,
    )


async def main() -> None:
    """Poll notification requests, persist intents, and deliver email safely."""
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is required for the notification worker.")

    database = Database(str(settings.database_url))
    worker_id = _worker_id(settings.notification_worker_id)
    http_client: httpx.AsyncClient | None = None

    outbox_policy = OutboxWorkerPolicy(
        batch_size=settings.notification_worker_batch_size
    )
    delivery_policy = NotificationDeliveryPolicy(
        batch_size=settings.notification_worker_batch_size
    )

    logger.info("notification_worker_started", worker_id=worker_id)
    last_digest_date: date | None = None

    try:
        sender, http_client = await _build_sender(settings)

        while True:
            try:
                current_time = datetime.now(UTC)
                digest_date = None
                digest_enqueued_count = 0
                async with database.session_factory() as session:
                    intent_result = await process_notification_request_events(
                        session,
                        worker_id=worker_id,
                        policy=outbox_policy,
                    )
                    if session.in_transaction():
                        await session.commit()
                    if (
                        current_time.hour >= settings.notification_digest_send_hour_utc
                        and last_digest_date != current_time.date()
                    ):
                        digest_enqueued_count = await enqueue_action_item_digests(
                            session,
                            now=current_time,
                        )
                        digest_date = current_time.date()
                        if session.in_transaction():
                            await session.commit()
                    delivered_count = await process_pending_notifications(
                        session,
                        worker_id=worker_id,
                        sender=sender,
                        policy=delivery_policy,
                        web_app_base_url=str(settings.web_app_base_url),
                    )

                if digest_date is not None:
                    last_digest_date = digest_date
                _record_heartbeat(settings.notification_worker_heartbeat_path)

                logger.info(
                    "notification_worker_cycle_complete",
                    worker_id=worker_id,
                    intents_claimed=intent_result.claimed,
                    intents_processed=intent_result.processed,
                    intents_dead_lettered=intent_result.dead_lettered,
                    digests_enqueued=digest_enqueued_count,
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
        try:
            if http_client is not None:
                await http_client.aclose()
        finally:
            await database.dispose()
        logger.info("notification_worker_stopped", worker_id=worker_id)


if __name__ == "__main__":
    asyncio.run(main())
