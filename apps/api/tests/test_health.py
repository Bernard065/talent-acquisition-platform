"""Tests for the health check endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_liveness_returns_ok() -> None:
    """Verify the liveness endpoint and required response headers."""
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "X-Request-ID" in response.headers
