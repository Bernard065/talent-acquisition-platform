"""FastAPI dependencies for authentication and request context."""

from typing import Annotated

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from app.core.authorization import TenantContext
from app.core.security import JwtVerifier

bearer_scheme = HTTPBearer(auto_error=False)
logger = structlog.get_logger()


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
