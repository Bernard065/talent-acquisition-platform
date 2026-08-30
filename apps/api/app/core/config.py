"""Application configuration and environment settings."""

from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables only."""

    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    app_name: str = "talent-acquisition-api"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: PostgresDsn | None = None
    redis_url: str = "redis://localhost:6379/0"

    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
