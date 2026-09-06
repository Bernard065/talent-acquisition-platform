"""FastAPI dependencies for authentication and request context."""

from collections.abc import AsyncIterator
from typing import Annotated, cast

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.core.security import JwtVerifier
from app.db.session import Database
from app.services.object_storage import ObjectStorage

bearer_scheme = HTTPBearer(auto_error=False)
logger = structlog.get_logger()


async def get_idempotency_key(
    idempotency_key: Annotated[
        str | None,
        Header(alias="Idempotency-Key"),
    ] = None,
) -> str:
    """Require an idempotency key for externally initiated write operations."""
    if idempotency_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    return idempotency_key


async def get_tenant_context(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> TenantContext:
    """Build caller context exclusively from verified access-token claims."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    request_id = request.headers.get("X-Request-ID", "unknown")
    verifier: JwtVerifier = request.app.state.jwt_verifier

    try:
        context = await run_in_threadpool(
            verifier.verify,
            credentials.credentials,
            request_id,
        )
    except InvalidTokenError:
        logger.warning("authentication_failed", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    structlog.contextvars.bind_contextvars(
        tenant_id=str(context.tenant_id),
        subject=context.subject,
    )
    return context


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide one database session for the current HTTP request."""
    database = getattr(request.app.state, "database", None)

    if not isinstance(database, Database):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
            headers={"Retry-After": "5"},
        )

    async with database.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_object_storage(request: Request) -> ObjectStorage:
    """Return the configured object-storage adapter for document workflows."""
    storage = getattr(request.app.state, "object_storage", None)

    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage service is unavailable.",
            headers={"Retry-After": "5"},
        )

    return cast(ObjectStorage, storage)
