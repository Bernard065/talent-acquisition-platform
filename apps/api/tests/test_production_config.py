"""Production configuration security validation tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    """Build valid production settings, allowing a focused override."""
    values: dict[str, object] = {
        "app_env": "production",
        "app_name": "tap-api",
        "app_version": "0.1.0",
        "api_prefix": "/api/v1",
        "log_level": "INFO",
        "database_url": "postgresql+asyncpg://tap:secret@postgres:5432/tap",
        "redis_url": "rediss://redis.internal:6379/0",
        "jwt_issuer": "https://identity.example.com/",
        "jwt_audience": "talent-acquisition-api",
        "jwt_jwks_url": "https://identity.example.com/.well-known/jwks.json",
        "jwt_algorithm": "RS256",
        "jwt_leeway_seconds": 30,
        "offer_signature_callback_provider": "none",
        "notification_email_provider": "resend",
        "notification_email_api_key_secret_name": "tap_resend_sending_api_key",
        "notification_email_from_address": "notifications@example.com",
        "credential_vault_provider": "infisical",
        "infisical_client_id": "tap-worker-client",
        "infisical_client_secret": "test-infisical-secret",
        "infisical_project_id": "tap-project",
    }
    values.update(overrides)
    return Settings(**values, _env_file=None)  # type: ignore[arg-type]


def test_accepts_secure_production_configuration() -> None:
    """Production accepts TLS-protected service and identity URLs."""
    settings = _settings()

    assert settings.rate_limiting_enabled is True
    assert settings.database_url is not None
    assert settings.redis_url.startswith("rediss://")
    assert settings.notification_email_provider == "resend"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"database_url": None}, "DATABASE_URL is required in production."),
        (
            {"redis_url": "redis://redis.internal:6379/0"},
            "REDIS_URL must use rediss:// in production.",
        ),
        (
            {"jwt_issuer": "http://identity.example.com/"},
            "JWT_ISSUER must use HTTPS in production.",
        ),
        (
            {"jwt_jwks_url": "http://identity.example.com/jwks.json"},
            "JWT_JWKS_URL must use HTTPS in production.",
        ),
    ],
)
def test_rejects_insecure_or_missing_production_settings(
    override: dict[str, object],
    message: str,
) -> None:
    """Unsafe production configuration fails with actionable errors."""
    with pytest.raises(ValidationError, match=message):
        _settings(**override)


def test_local_environment_can_use_local_redis_and_http_identity_urls() -> None:
    """Local development can keep Compose Redis and local identity URLs."""
    settings = Settings(
        app_env="local",
        app_name="tap-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        redis_url="redis://localhost:6379/0",
        jwt_issuer="http://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="http://issuer.example.test/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )

    assert settings.redis_url.startswith("redis://")


def test_production_rejects_local_logging_email_adapter() -> None:
    """The local logging adapter must never silently discard production mail."""
    with pytest.raises(
        ValidationError,
        match="NOTIFICATION_EMAIL_PROVIDER=resend is required in production",
    ):
        _settings(notification_email_provider="logging")


def test_production_rejects_local_job_board_provider() -> None:
    """The no-network fake adapter cannot be selected in production."""
    with pytest.raises(
        ValidationError,
        match="JOB_BOARD_PROVIDER=local is permitted only in local and test",
    ):
        _settings(job_board_provider="local")
