"""Privacy-conscious OpenTelemetry tracing runtime for the API."""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span
from sqlalchemy.engine import Engine

_URL_ATTRIBUTES = frozenset(
    {
        "url.full",
        "url.path",
        "url.query",
        "http.url",
        "http.target",
    }
)


def _route_category(scope: dict[str, Any]) -> str:
    """Map request paths to fixed labels without retaining path segments."""
    path = str(scope.get("path", ""))
    segments = path.strip("/").split("/")
    method = str(scope.get("method", "")).upper()

    if segments[-2:] in (["health", "live"], ["health", "ready"]):
        return "health"
    if segments[-1:] == ["callbacks"] and "offer-signatures" in segments:
        return "signature-callback"
    if (
        method == "POST"
        and len(segments) >= 4
        and segments[-3] == "jobs"
        and segments[-1] == "applications"
    ):
        return "public-application"
    if (
        method == "GET"
        and any(
            segments[index : index + 2] == ["public", "jobs"]
            for index in range(max(0, len(segments) - 3), len(segments) - 1)
        )
    ):
        return "public-read"
    if segments and segments[0] == "api":
        return "api"
    return "other"


def _redact_span(span: Span, *, method: str, category: str) -> None:
    """Keep only method and bounded category; overwrite URL/header identity data."""
    if not span.is_recording():
        return

    span.update_name(f"HTTP {method}")
    span.set_attribute("tap.route_category", category)
    span_attributes = getattr(span, "attributes", None)
    for attribute in tuple((span_attributes or {}).keys()):
        if (
            attribute in _URL_ATTRIBUTES
            or attribute in {"client.address", "network.peer.address"}
            or attribute.startswith("http.request.header.")
            or attribute.startswith("http.response.header.")
        ):
            span.set_attribute(attribute, "[REDACTED]")


def _server_request_hook(span: Span, scope: dict[str, Any]) -> None:
    """Sanitize server spans before application code handles the request."""
    method = str(scope.get("method", "UNKNOWN")).upper()
    _redact_span(span, method=method, category=_route_category(scope))


def _client_request_hook(span: Span, request: Any) -> None:
    """Remove outbound URL and captured header values from client spans."""
    method = str(getattr(request, "method", "HTTP")).upper()
    _redact_span(span, method=method, category="outbound")


class TracingRuntime:
    """Own instrumentation registrations and SDK shutdown for one API app."""

    def __init__(
        self,
        application: FastAPI,
        *,
        service_name: str,
        service_version: str,
        environment: str,
        sample_ratio: float,
        exporter: SpanExporter | None = None,
    ) -> None:
        """Create the SDK provider and instrument FastAPI, SQLAlchemy, and HTTPX."""
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment.name": environment,
            }
        )
        self.provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(root=TraceIdRatioBased(sample_ratio)),
        )
        self.provider.add_span_processor(
            BatchSpanProcessor(exporter or OTLPSpanExporter())
        )
        self.application = application
        self._sqlalchemy_instrumentor = SQLAlchemyInstrumentor()
        self._httpx_instrumentor = HTTPXClientInstrumentor()
        self._instrumented_engine: Engine | None = None
        self._closed = False

        FastAPIInstrumentor.instrument_app(
            application,
            tracer_provider=self.provider,
            server_request_hook=_server_request_hook,
            http_capture_headers_server_request=[],
            http_capture_headers_server_response=[],
        )
        self._httpx_instrumentor.instrument(
            tracer_provider=self.provider,
            request_hook=_client_request_hook,
        )

    def instrument_engine(self, engine: Engine) -> None:
        """Instrument the app's SQLAlchemy engine without SQL comments."""
        self._instrumented_engine = engine
        self._sqlalchemy_instrumentor.instrument(
            engine=engine,
            tracer_provider=self.provider,
            enable_commenter=False,
        )

    def shutdown(self) -> None:
        """Flush spans and detach instrumentation during app shutdown."""
        if self._closed:
            return

        self._httpx_instrumentor.uninstrument()
        if self._instrumented_engine is not None:
            self._sqlalchemy_instrumentor.uninstrument(
                engine=self._instrumented_engine,
            )
        FastAPIInstrumentor.uninstrument_app(self.application)
        self.provider.force_flush(timeout_millis=5_000)
        self.provider.shutdown()
        self._closed = True


def build_tracing_runtime(
    application: FastAPI,
    *,
    enabled: bool,
    service_name: str,
    service_version: str,
    environment: str,
    sample_ratio: float,
    exporter_factory: Callable[[], SpanExporter] | None = None,
) -> TracingRuntime | None:
    """Build tracing only when explicitly enabled for this service process."""
    if not enabled:
        return None

    return TracingRuntime(
        application,
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        sample_ratio=sample_ratio,
        exporter=exporter_factory() if exporter_factory is not None else None,
    )
