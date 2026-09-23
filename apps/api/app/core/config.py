"""Application configuration and environment settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = API_ROOT.parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment variables only."""

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"]
    app_name: str
    app_version: str
    api_prefix: str

    log_level: str = Field(
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )

    database_url: PostgresDsn | None = None
    redis_url: str
    allowed_origins: list[str] = Field(default_factory=list)
    security_hsts_max_age_seconds: int = Field(
        default=31_536_000,
        ge=0,
        le=63_072_000,
    )
    # OAuth callbacks are server-controlled. Never accept redirect URIs from API requests.
    calendar_google_oauth_redirect_uri: AnyHttpUrl | None = None
    calendar_microsoft_oauth_redirect_uri: AnyHttpUrl | None = None

    # Object storage. The adapter validates these when it is constructed.
    s3_endpoint_url: AnyHttpUrl | None = None
    s3_public_endpoint_url: AnyHttpUrl | None = None
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_bucket: str | None = Field(
        default=None,
        min_length=3,
        max_length=63,
        pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$",
    )
    s3_region: str | None = Field(default=None, min_length=1, max_length=64)
    s3_presigned_upload_expiry_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
    )

    # Malware scanning; ClamAV is reachable only on the private container network.
    clamav_host: str = Field(default="clamav", min_length=1, max_length=255)
    clamav_port: int = Field(default=3310, ge=1, le=65535)
    clamav_timeout_seconds: int = Field(default=120, ge=1, le=300)
    clamav_max_stream_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        le=100 * 1024 * 1024,
    )

    scan_worker_poll_interval_seconds: int = Field(default=2, ge=1, le=60)
    scan_worker_batch_size: int = Field(default=10, ge=1, le=100)
    scan_worker_id: str | None = Field(default=None, min_length=1, max_length=255)
    scan_worker_metrics_port: int = Field(default=9100, ge=1024, le=65535)
    scan_worker_heartbeat_path: Path = Path(
        "/tmp/tap-document-scan-worker.heartbeat"  # noqa: S108
    )
    scan_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=5,
        le=600,
    )
    offer_expiry_worker_poll_interval_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
    )
    offer_expiry_worker_batch_size: int = Field(
        default=50,
        ge=1,
        le=100,
    )
    offer_expiry_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    offer_expiry_worker_heartbeat_path: Path = Path(
        "/tmp/tap-offer-expiry-worker.heartbeat"  # noqa: S108
    )
    offer_expiry_worker_heartbeat_max_age_seconds: int = Field(
        default=120,
        ge=10,
        le=900,
    )
    job_posting_expiry_worker_poll_interval_seconds: int = Field(
        default=60,
        ge=1,
        le=300,
    )
    job_posting_expiry_worker_batch_size: int = Field(
        default=50,
        ge=1,
        le=100,
    )
    job_posting_expiry_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    job_posting_expiry_worker_heartbeat_path: Path = Path(
        "/tmp/tap-job-posting-expiry-worker.heartbeat"  # noqa: S108
    )
    job_posting_expiry_worker_heartbeat_max_age_seconds: int = Field(
        default=180,
        ge=10,
        le=900,
    )
    notification_worker_poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
    )
    notification_worker_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )
    notification_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    notification_worker_heartbeat_path: Path = Path(
        "/tmp/tap-notification-worker.heartbeat"  # noqa: S108
    )
    notification_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=10,
        le=900,
    )
    calendar_sync_worker_poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
    )
    calendar_sync_worker_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )
    calendar_sync_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    calendar_sync_worker_heartbeat_path: Path = Path(
        "/tmp/tap-calendar-sync-worker.heartbeat"  # noqa: S108
    )
    calendar_sync_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=10,
        le=900,
    )
    webhook_delivery_worker_poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
    )
    webhook_delivery_worker_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )
    webhook_delivery_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    webhook_delivery_worker_heartbeat_path: Path = Path(
        "/tmp/tap-webhook-delivery-worker.heartbeat"  # noqa: S108
    )
    webhook_delivery_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=10,
        le=900,
    )
    webhook_delivery_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
    )
    webhook_allowed_hosts: list[str] = Field(default_factory=list)
    offer_signature_provider: Literal["none", "local"] = "none"
    offer_signature_callback_provider: Literal["none", "local"] = "none"
    offer_signature_callback_local_signing_secret: SecretStr | None = None
    offer_signature_callback_max_body_bytes: int = Field(
        default=64 * 1024,
        ge=1_024,
        le=1_048_576,
    )
    offer_signature_dispatch_worker_poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=300,
    )
    offer_signature_dispatch_worker_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )
    offer_signature_dispatch_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    offer_signature_dispatch_worker_heartbeat_path: Path = Path(
        "/tmp/tap-offer-signature-dispatch-worker.heartbeat"  # noqa: S108
    )
    offer_signature_dispatch_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=10,
        le=900,
    )
    offer_signature_expiry_worker_poll_interval_seconds: int = Field(
        default=60,
        ge=1,
        le=300,
    )
    offer_signature_expiry_worker_batch_size: int = Field(
        default=50,
        ge=1,
        le=100,
    )
    offer_signature_expiry_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    offer_signature_expiry_worker_heartbeat_path: Path = Path(
        "/tmp/tap-offer-signature-expiry-worker.heartbeat"  # noqa: S108
    )
    offer_signature_expiry_worker_heartbeat_max_age_seconds: int = Field(
        default=180,
        ge=10,
        le=900,
    )

    hris_handoff_provider: Literal["none", "bamboohr"] = "none"
    hris_handoff_worker_poll_interval_seconds: int = Field(
        default=10,
        ge=1,
        le=300,
    )
    hris_handoff_worker_batch_size: int = Field(
        default=25,
        ge=1,
        le=100,
    )
    hris_handoff_worker_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    hris_handoff_worker_heartbeat_path: Path = Path(
        "/tmp/tap-hris-handoff-worker.heartbeat"  # noqa: S108
    )
    hris_handoff_worker_heartbeat_max_age_seconds: int = Field(
        default=90,
        ge=10,
        le=900,
    )
    hris_handoff_http_connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=30,
    )
    hris_handoff_http_read_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        le=60,
    )

    public_application_abuse_control_provider: Literal[
        "local_allow_all",
        "captcha",
    ] = "local_allow_all"

    jwt_issuer: AnyHttpUrl
    jwt_audience: str = Field(min_length=1)
    jwt_jwks_url: AnyHttpUrl
    jwt_algorithm: Literal["RS256"]
    jwt_leeway_seconds: int = Field(ge=0, le=300)

    calendar_oauth_provider: Literal["none", "google"] = "none"
    google_calendar_oauth_client_id_secret_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    google_calendar_oauth_client_secret_secret_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
    )
    calendar_oauth_http_connect_timeout_seconds: float = Field(
        default=3.0,
        gt=0,
        le=30,
    )
    calendar_oauth_http_read_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=60,
    )

    # External credential vault for calendar OAuth tokens.
    credential_vault_provider: Literal[
        "infisical",
        "none",
    ] = "none"
    infisical_client_id: str | None = None
    infisical_client_secret: SecretStr | None = None
    infisical_project_id: str | None = None
    infisical_environment: str = "dev"
    infisical_host: AnyHttpUrl = AnyHttpUrl("https://app.infisical.com")

    @model_validator(mode="after")
    def _validate_vault_provider(self) -> "Settings":
        if self.credential_vault_provider == "infisical":
            missing = [
                name
                for name in (
                    "infisical_client_id",
                    "infisical_client_secret",
                    "infisical_project_id",
                )
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(f.upper() for f in missing)} required when "
                    "CREDENTIAL_VAULT_PROVIDER=infisical."
                )

        if self.calendar_oauth_provider == "google":
            if self.credential_vault_provider != "infisical":
                raise ValueError(
                    "credential_vault_provider must be 'infisical' when "
                    "calendar_oauth_provider is 'google'."
                )

            if not self.google_calendar_oauth_client_id_secret_name:
                raise ValueError(
                    "google_calendar_oauth_client_id_secret_name is required "
                    "when calendar_oauth_provider is 'google'."
                )

            if not self.google_calendar_oauth_client_secret_secret_name:
                raise ValueError(
                    "google_calendar_oauth_client_secret_secret_name is "
                    "required when calendar_oauth_provider is 'google'."
                )

        if self.offer_signature_callback_provider == "local":
            if self.app_env not in {"local", "test"}:
                raise ValueError(
                    "offer_signature_callback_provider='local' is permitted "
                    "only in local or test environments."
                )

            local_callback_secret = (
                self.offer_signature_callback_local_signing_secret
            )
            if (
                local_callback_secret is None
                or not local_callback_secret.get_secret_value()
            ):
                raise ValueError(
                    "offer_signature_callback_local_signing_secret is required "
                    "when offer_signature_callback_provider='local'."
                )

        if self.hris_handoff_provider != "none":
            if self.credential_vault_provider != "infisical":
                raise ValueError(
                    "credential_vault_provider must be 'infisical' when "
                    "hris_handoff_provider is enabled."
                )

        if (
            self.app_env == "production"
            and self.security_hsts_max_age_seconds == 0
        ):
            raise ValueError(
                "security_hsts_max_age_seconds must be greater than zero "
                "in production."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()  # type: ignore[call-arg]
