"""Privacy and lifecycle tests for API tracing instrumentation."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind
from sqlalchemy import create_engine, text

from app.observability.tracing import TracingRuntime, build_tracing_runtime


def test_server_spans_do_not_export_candidate_url_or_query_values() -> None:
    """Server traces keep safe route labels but redact identifying URL values."""
    candidate_email = "candidate-sensitive@example.test"
    query_email = "query-sensitive@example.test"
    application = FastAPI()

    @application.get("/api/v1/candidates/{candidate_id}")
    async def get_candidate(candidate_id: str) -> dict[str, str]:
        return {"id": candidate_id}

    exporter = InMemorySpanExporter()
    runtime = TracingRuntime(
        application,
        service_name="tap-api-test",
        service_version="test",
        environment="test",
        sample_ratio=1.0,
        exporter=exporter,
    )

    try:
        with TestClient(application) as client:
            response = client.get(
                f"/api/v1/candidates/{candidate_email}",
                params={"email": query_email},
                headers={"Authorization": "Bearer synthetic-test-token"},
            )
        assert response.status_code == 200
    finally:
        runtime.shutdown()

    spans = exporter.get_finished_spans()
    server_spans = [span for span in spans if span.kind is SpanKind.SERVER]

    assert server_spans
    for span in spans:
        rendered_span = f"{span.name} {span.attributes}"
        assert candidate_email not in rendered_span
        assert query_email not in rendered_span
        assert "synthetic-test-token" not in rendered_span

    candidate_span = server_spans[0]
    assert candidate_span.attributes["tap.route_category"] == "api"
    redacted_url_attributes = {
        key: value
        for key, value in candidate_span.attributes.items()
        if key in {"url.full", "url.path", "url.query", "http.url", "http.target"}
    }
    assert redacted_url_attributes
    assert set(redacted_url_attributes.values()) == {"[REDACTED]"}


def test_tracing_runtime_is_omitted_when_disabled() -> None:
    """Disabled tracing does not install exporters or instrumentors."""
    application = FastAPI()

    runtime = build_tracing_runtime(
        application,
        enabled=False,
        service_name="tap-api",
        service_version="0.1.0",
        environment="local",
        sample_ratio=0.1,
    )

    assert runtime is None


def test_sqlalchemy_spans_do_not_capture_bound_candidate_values() -> None:
    """Database spans preserve query visibility without parameter values."""
    candidate_email = "database-sensitive@example.test"
    application = FastAPI()
    exporter = InMemorySpanExporter()
    runtime = TracingRuntime(
        application,
        service_name="tap-api-test",
        service_version="test",
        environment="test",
        sample_ratio=1.0,
        exporter=exporter,
    )
    engine = create_engine("sqlite:///:memory:")
    runtime.instrument_engine(engine)

    try:
        with engine.connect() as connection:
            connection.execute(
                text("SELECT :candidate_email"),
                {"candidate_email": candidate_email},
            )
    finally:
        engine.dispose()
        runtime.shutdown()

    spans = exporter.get_finished_spans()

    assert spans
    assert any("db.system" in span.attributes for span in spans)
    assert all(candidate_email not in str(span.attributes) for span in spans)
