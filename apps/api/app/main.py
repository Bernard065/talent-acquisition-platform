"""FastAPI application factory and application lifecycle management."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.exception_handlers import register_exception_handlers
from app.api.v1.applications import router as applications_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.candidates import router as candidates_router
from app.api.v1.documents import router as documents_router
from app.api.v1.health import router as health_router
from app.api.v1.hiring_decisions import router as hiring_decisions_router
from app.api.v1.identity import router as identity_router
from app.api.v1.interview_feedback import router as interview_feedback_router
from app.api.v1.interview_lifecycle import router as interview_lifecycle_router
from app.api.v1.interview_search import router as interview_search_router
from app.api.v1.interviews import router as interviews_router
from app.api.v1.job_postings import router as job_postings_router
from app.api.v1.notification_preferences import (
    router as notification_preferences_router,
)
from app.api.v1.offers import router as offers_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.operations import router as operations_router
from app.api.v1.public_applications import (
    router as public_applications_router,
)
from app.api.v1.public_jobs import router as public_jobs_router
from app.api.v1.requisitions import router as requisitions_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import JwtVerifier
from app.db.session import Database
from app.infrastructure.object_storage.s3 import S3ObjectStorage
from app.services.public_application_abuse_control import (
    build_public_application_abuse_guard,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources on startup and clean them up on shutdown."""
    settings: Settings = application.state.settings
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

    logger.info("application_started", environment=settings.app_env)

    yield

    if application.state.database is not None:
        await application.state.database.dispose()

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

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
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

    return application


app = create_app()
