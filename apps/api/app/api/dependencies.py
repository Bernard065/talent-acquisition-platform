"""FastAPI dependencies for authentication and request context."""

from collections.abc import AsyncIterator, Mapping
from typing import Annotated, cast

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import TenantContext
from app.core.security import JwtVerifier, TokenClaims
from app.db.session import Database
from app.domains.calendar.enums import CalendarProvider
from app.services.abuse_control import PublicApplicationAbuseGuard
from app.services.calendar_credentials import CalendarCredentialVault
from app.services.calendar_oauth import (
    CalendarOAuthProvider,
    CalendarOAuthStateStore,
)
from app.services.hris_credentials import HrisCredentialVault
from app.services.object_storage import ObjectStorage
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerifier,
)
from app.services.tenant_identity import (
    Auth0OrganizationNotMappedError,
    resolve_auth0_organization_tenant_id,
)
from app.services.webhook_secrets import WebhookSigningSecretVault

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


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Provide one database session for the current HTTP request."""
    database = getattr(request.app.state, "database", None)

    if not isinstance(database, Database):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    async with database.session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_verified_token_claims(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> TokenClaims:
    """Verify bearer credentials and return only the signed Auth0 claims."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    cached_claims = getattr(request.state, "verified_auth0_claims", None)
    if isinstance(cached_claims, TokenClaims):
        return cached_claims

    request_id = request.headers.get("X-Request-ID", "unknown")
    verifier: JwtVerifier = request.app.state.jwt_verifier
    try:
        claims = await run_in_threadpool(
            verifier.verify,
            credentials.credentials,
        )
    except InvalidTokenError:
        logger.warning("authentication_failed", request_id=request_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    request.state.verified_auth0_claims = claims
    return claims


async def get_tenant_context(
    request: Request,
    claims: Annotated[TokenClaims, Depends(get_verified_token_claims)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantContext:
    """Resolve the verified Auth0 Organization to an internal tenant."""
    request_id = request.headers.get("X-Request-ID", "unknown")
    try:
        tenant_id = await resolve_auth0_organization_tenant_id(
            session,
            organization_id=claims.org_id,
        )
    except Auth0OrganizationNotMappedError:
        logger.warning(
            "authentication_organization_not_mapped",
            request_id=request_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permission.",
        ) from None

    context = TenantContext(
        tenant_id=tenant_id,
        subject=claims.sub,
        roles=frozenset(claims.roles),
        request_id=request_id,
    )
    structlog.contextvars.bind_contextvars(
        tenant_id=str(context.tenant_id),
        subject=context.subject,
    )
    return context


async def get_object_storage(request: Request) -> ObjectStorage:
    """Return the configured object-storage adapter for document workflows."""
    storage = getattr(request.app.state, "object_storage", None)

    if storage is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document storage service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(ObjectStorage, storage)


_PUBLIC_APPLICATION_MAX_BODY_BYTES = 16 * 1024


async def get_public_application_abuse_guard(
    request: Request,
) -> PublicApplicationAbuseGuard:
    """Return the configured anonymous-submission abuse-control provider."""
    guard = getattr(request.app.state, "public_application_abuse_guard", None)
    if guard is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application submission service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(PublicApplicationAbuseGuard, guard)


async def enforce_public_application_body_limit(request: Request) -> None:
    """Reject oversized anonymous submissions before application processing."""
    content_length = request.headers.get("Content-Length")

    if content_length is not None:
        try:
            if int(content_length) > _PUBLIC_APPLICATION_MAX_BODY_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Application submission is too large.",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
            ) from None

    body = await request.body()
    if len(body) > _PUBLIC_APPLICATION_MAX_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Application submission is too large.",
        )


async def get_calendar_oauth_state_store(
    request: Request,
) -> CalendarOAuthStateStore:
    """Return the configured one-time OAuth state store."""
    state_store = getattr(request.app.state, "calendar_oauth_state_store", None)
    if state_store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calendar authorization service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(CalendarOAuthStateStore, state_store)


async def get_calendar_oauth_providers(
    request: Request,
) -> Mapping[CalendarProvider, CalendarOAuthProvider]:
    """Return configured provider adapters without exposing their credentials."""
    providers = getattr(request.app.state, "calendar_oauth_providers", None)
    if providers is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calendar authorization service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(Mapping[CalendarProvider, CalendarOAuthProvider], providers)


async def get_calendar_credential_vault(
    request: Request,
) -> CalendarCredentialVault:
    """Return the configured external credential vault."""
    credential_vault = getattr(
        request.app.state,
        "calendar_credential_vault",
        None,
    )
    if credential_vault is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calendar authorization service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(CalendarCredentialVault, credential_vault)


async def get_webhook_signing_secret_vault(
    request: Request,
) -> WebhookSigningSecretVault:
    """Return the configured vault used only for outbound webhook secrets."""

    vault = getattr(request.app.state, "webhook_signing_secret_vault", None)

    if vault is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook management service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(WebhookSigningSecretVault, vault)


async def get_hris_credential_vault(
    request: Request,
) -> HrisCredentialVault:
    """Return the external vault used for tenant-managed HRIS credentials."""
    vault = getattr(request.app.state, "hris_credential_vault", None)

    if vault is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HRIS management service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return cast(HrisCredentialVault, vault)


async def get_offer_signature_callback_verifiers(
    request: Request,
) -> Mapping[str, OfferSignatureCallbackVerifier]:
    """Return configured trusted offer-signature callback verifiers."""
    verifiers = getattr(
        request.app.state,
        "offer_signature_callback_verifiers",
        None,
    )

    if verifiers is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signature callback service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "no-store",
            },
        )

    return cast(Mapping[str, OfferSignatureCallbackVerifier], verifiers)
