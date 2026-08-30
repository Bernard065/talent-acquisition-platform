"""FastAPI application factory and application lifecycle management."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.api.v1.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import Database

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize application resources on startup and clean them up on shutdown."""
    settings: Settings = application.state.settings
    configure_logging(settings.log_level)

    if settings.database_url is not None:
        application.state.database = Database(str(settings.database_url))
    else:
        application.state.database = None

    logger.info("application_started", environment=settings.app_env)

    yield

    if application.state.database is not None:
        await application.state.database.dispose()
    logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    active_settings = settings or get_settings()

    application = FastAPI(
        title="Talent Acquisition Platform API",
        version="0.1.0",
        openapi_url=f"{active_settings.api_prefix}/openapi.json",
        docs_url=f"{active_settings.api_prefix}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    application.state.settings = active_settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
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

    return application


app = create_app()
