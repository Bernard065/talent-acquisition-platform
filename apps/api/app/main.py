"""FastAPI application factory and application lifecycle management."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from http.server import HTTPServer
from threading import Thread
from uuid import uuid4

import httpx
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace as otel_trace
from prometheus_client import start_http_server
from starlette.responses import Response

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.applications import router as applications_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.calendar_connections import (
    router as calendar_connections_router,
)
from app.api.v1.candidate_retention_reviews import (
    router as candidate_retention_reviews_router,
)
from app.api.v1.candidates import router as candidates_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.hiring_decisions import router as hiring_decisions_router
from app.api.v1.hris_connections import (
    router as hris_connections_router,
)
from app.api.v1.hris_handoffs import (
    router as hris_handoffs_router,
)
from app.api.v1.identity import router as identity_router
from app.api.v1.interview_feedback import router as interview_feedback_router
from app.api.v1.interview_lifecycle import router as interview_lifecycle_router
from app.api.v1.interview_search import router as interview_search_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.job_postings import router as job_postings_router
from app.api.v1.notification_preferences import (
    router as notification_preferences_router,
)
from app.api.v1.offer_signature_callbacks import (
    router as offer_signature_callbacks_router,
)
from app.api.v1.offers import router as offers_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.operations import router as operations_router
from app.api.v1.public_applications import (
    router as public_applications_router,
)
from app.api.v1.public_jobs import router as public_jobs_router
from app.api.v1.recruiting_metrics import (
    router as recruiting_metrics_router,
)
from app.api.v1.requisitions import router as requisitions_router
from app.api.v1.webhooks import (
    router as webhooks_router,  # pyright: ignore[reportAttributeAccessIssue]
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.rate_limit_middleware import enforce_request_rate_limit
from app.core.security import JwtVerifier
from app.db.session import Database
from app.domains.calendar.enums import CalendarProvider
from app.infrastructure.calendar.google_oauth import GoogleCalendarOAuthProvider
from app.infrastructure.calendar.infisical_vault import InfisicalCredentialVault
from app.infrastructure.hris.infisical_vault import (
    InfisicalHrisCredentialVault,
)
from app.infrastructure.object_storage.s3 import S3ObjectStorage
from app.infrastructure.rate_limiting.redis import RedisRateLimiter
from app.infrastructure.signatures.local_callback_verifier import (
    LocalOfferSignatureCallbackVerifier,
)
from app.observability.tracing import build_tracing_runtime
from app.services.public_application_abuse_control import (
    build_public_application_abuse_guard,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources on startup and clean them up on shutdown."""
    settings: Settings = application.state.settings
    application.state.calendar_credential_vault = None
    application.state.calendar_credential_resolver = None
    application.state.hris_credential_vault = None
    application.state.webhook_signing_secret_vault = None
    application.state.calendar_oauth_providers = {}
    application.state.offer_signature_callback_verifiers = {}
    application.state.rate_limiter = None
    application.state.tracing_runtime = None

    oauth_http_client: httpx.AsyncClient | None = None
    metrics_server: HTTPServer | None = None
    metrics_thread: Thread | None = None

    configure_logging(settings.log_level)

    application.state.jwt_verifier = JwtVerifier(settings)

    if settings.database_url is not None:
        application.state.database = Database(str(settings.database_url))
    else:
        application.state.database = None

    storage_configuration_present = any(
        (
            settings.s3_endpoint_url,
            settings.s3_public_endpoint_url,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_bucket,
            settings.s3_region,
        )
    )

    application.state.object_storage = (
        S3ObjectStorage.from_settings(settings)
        if storage_configuration_present
        else None
    )

    if settings.credential_vault_provider == "infisical":
        vault = await InfisicalCredentialVault.from_universal_auth(
            project_id=settings.infisical_project_id,  # type: ignore[arg-type]
            environment_slug=settings.infisical_environment,
            client_id=settings.infisical_client_id,  # type: ignore[arg-type]
            client_secret=settings.infisical_client_secret.get_secret_value(),  # type: ignore[union-attr]
            host=str(settings.infisical_host),
        )
        application.state.calendar_credential_vault = vault
        application.state.calendar_credential_resolver = vault
        application.state.hris_credential_vault = (
            await InfisicalHrisCredentialVault.from_universal_auth(
                project_id=settings.infisical_project_id,  # type: ignore[arg-type]
                environment_slug=settings.infisical_environment,
                client_id=settings.infisical_client_id,  # type: ignore[arg-type]
                client_secret=settings.infisical_client_secret.get_secret_value(),  # type: ignore[union-attr]
                host=str(settings.infisical_host),
            )
        )
        application.state.webhook_signing_secret_vault = vault

    if settings.calendar_oauth_provider == "google":
        vault = application.state.calendar_credential_vault
        if vault is None:
            raise RuntimeError(
                "Google Calendar OAuth requires an initialized credential vault."
            )

        client_id_secret = await vault.read_runtime_secret(
            secret_name=settings.google_calendar_oauth_client_id_secret_name,
        )
        client_secret = await vault.read_runtime_secret(
            secret_name=settings.google_calendar_oauth_client_secret_secret_name,
        )

        oauth_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.calendar_oauth_http_connect_timeout_seconds,
                read=settings.calendar_oauth_http_read_timeout_seconds,
                write=settings.calendar_oauth_http_read_timeout_seconds,
                pool=settings.calendar_oauth_http_connect_timeout_seconds,
            ),
            follow_redirects=False,
        )

        application.state.calendar_oauth_providers = {
            CalendarProvider.GOOGLE: GoogleCalendarOAuthProvider(
                client_id=client_id_secret.get_secret_value(),
                client_secret=client_secret,
                http_client=oauth_http_client,
            ),
        }

    if settings.offer_signature_callback_provider == "local":
        callback_secret = settings.offer_signature_callback_local_signing_secret
        if callback_secret is None:
            raise RuntimeError(
                "Local offer-signature callback secret is not configured."
            )

        application.state.offer_signature_callback_verifiers = {
            "local": LocalOfferSignatureCallbackVerifier(
                signing_secret=callback_secret,
            ),
        }

    if settings.rate_limiting_enabled:
        application.state.rate_limiter = RedisRateLimiter.from_url(
            settings.redis_url,
        )
        metrics_server, metrics_thread = start_http_server(
            settings.api_metrics_port,
            addr="0.0.0.0",
        )

    tracing_runtime = build_tracing_runtime(
        application,
        enabled=settings.tracing_enabled,
        service_name=settings.app_name,
        service_version=settings.app_version,
        environment=settings.app_env,
        sample_ratio=settings.tracing_sample_ratio,
    )
    application.state.tracing_runtime = tracing_runtime
    database = application.state.database
    if tracing_runtime is not None and database is not None:
        tracing_runtime.instrument_engine(database.engine.sync_engine)

    try:
        logger.info("application_started", environment=settings.app_env)
        yield
    finally:
        if oauth_http_client is not None:
            await oauth_http_client.aclose()

        if tracing_runtime is not None:
            tracing_runtime.shutdown()

        if metrics_server is not None:
            metrics_server.shutdown()
            metrics_server.server_close()
        if metrics_thread is not None:
            metrics_thread.join(timeout=5)

        try:
            rate_limiter = getattr(application.state, "rate_limiter", None)
            if rate_limiter is not None:
                await rate_limiter.close()
        finally:
            database = getattr(application.state, "database", None)
            if database is not None:
                await database.dispose()

        logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    active_settings = settings or get_settings()

    application = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        openapi_url=f"{active_settings.api_prefix}/openapi.json",
        docs_url=f"{active_settings.api_prefix}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    application.state.settings = active_settings
    application.state.public_application_abuse_guard = (
        build_public_application_abuse_guard(active_settings)
    )
    application.state.offer_signature_callback_verifiers = {}
    application.state.rate_limiter = None

    register_exception_handlers(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-ID",
        ],
    )

    @application.middleware("http")
    async def request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Attach a request ID and security headers to each response."""
        request_id = request.headers.get("X-Request-ID", str(uuid4()))

        # Do not trust a caller-provided identity or tenant header.
        structlog.contextvars.bind_contextvars(request_id=request_id)
        span_context = otel_trace.get_current_span().get_span_context()
        if span_context.is_valid:
            structlog.contextvars.bind_contextvars(
                trace_id=f"{span_context.trace_id:032x}",
                span_id=f"{span_context.span_id:016x}",
            )

        try:
            rate_limit_response = await enforce_request_rate_limit(request)
            if rate_limit_response is not None:
                response = rate_limit_response
            else:
                response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), geolocation=(), microphone=(), payment=(), usb=()"
            )
            response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

            if active_settings.app_env == "production":
                response.headers["Strict-Transport-Security"] = (
                    "max-age="
                    f"{active_settings.security_hsts_max_age_seconds}; "
                    "includeSubDomains"
                )

            return response
        finally:
            structlog.contextvars.clear_contextvars()

    application.include_router(
        health_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        public_jobs_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        public_applications_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        identity_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        calendar_connections_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        requisitions_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        approvals_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        candidates_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        candidate_retention_reviews_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        job_postings_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        applications_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        hiring_decisions_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        offers_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        onboarding_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        notification_preferences_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        interviews_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        interview_search_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        interview_lifecycle_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        interview_feedback_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        documents_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        operations_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        recruiting_metrics_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        webhooks_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        offer_signature_callbacks_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        hris_connections_router,
        prefix=active_settings.api_prefix,
    )

    application.include_router(
        hris_handoffs_router,
        prefix=active_settings.api_prefix,
    )

    application.state.tracing_runtime = None

    return application


app = create_app()
