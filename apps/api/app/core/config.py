"""Application configuration and environment settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Application configuration loaded from environment variables only."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
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

    # Identity provider contract
    jwt_issuer: AnyHttpUrl
    jwt_audience: str = Field(min_length=1)
    jwt_jwks_url: AnyHttpUrl
    jwt_algorithm: Literal["RS256"]
    jwt_leeway_seconds: int = Field(ge=0, le=300)


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings.model_validate({})
