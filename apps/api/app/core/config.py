"""Application configuration and environment settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, SecretStr
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

    jwt_issuer: AnyHttpUrl
    jwt_audience: str = Field(min_length=1)
    jwt_jwks_url: AnyHttpUrl
    jwt_algorithm: Literal["RS256"]
    jwt_leeway_seconds: int = Field(ge=0, le=300)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()  # type: ignore[call-arg]
