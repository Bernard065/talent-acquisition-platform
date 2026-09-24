"""Tests for API transport-security response headers."""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _settings(app_env: str) -> Settings:
    """Create a minimal runtime configuration for header tests."""
    return Settings(
        app_env=app_env,
        app_name="tap-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        database_url=(
            "postgresql+asyncpg://tap:test-password@localhost:5432/tap"
            if app_env == "production"
            else None
        ),
        redis_url=(
            "rediss://redis.example.test:6379/0"
            if app_env == "production"
            else "redis://localhost:6379/0"
        ),
        public_application_abuse_control_provider="local_allow_all",
        offer_signature_callback_provider="none",
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
    )


def test_security_headers_are_applied_to_api_responses() -> None:
    """Every response receives browser-safety headers."""
    with TestClient(create_app(_settings("local"))) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == (
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
    )
    assert response.headers["X-Permitted-Cross-Domain-Policies"] == "none"
    assert "Strict-Transport-Security" not in response.headers


def test_hsts_is_emitted_only_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production enables HTTPS persistence without affecting local development."""
    monkeypatch.setattr(
        "app.main.build_public_application_abuse_guard",
        lambda settings: object(),
    )

    with TestClient(create_app(_settings("production"))) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )
