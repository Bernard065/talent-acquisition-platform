"""Private OAuth endpoints for user-owned calendar connections."""

from collections.abc import Mapping
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_calendar_credential_vault,
    get_calendar_oauth_providers,
    get_calendar_oauth_state_store,
    get_db_session,
    get_tenant_context,
)
from app.api.v1.schemas.calendar_connections import (
    CalendarAuthorizationUrlResponse,
    CalendarConnectionResponse,
)
from app.core.authorization import TenantContext
from app.core.config import Settings
from app.domains.calendar.enums import CalendarProvider
from app.services.calendar_connections import (
    begin_calendar_authorization,
    complete_calendar_authorization,
)
from app.services.calendar_credentials import CalendarCredentialVault
from app.services.calendar_oauth import (
    CalendarOAuthProvider,
    CalendarOAuthStateStore,
)

router = APIRouter(
    prefix="/calendar-connections",
    tags=["Calendar connections"],
)

CallerContext = Annotated[TenantContext, Depends(get_tenant_context)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
OAuthStateStore = Annotated[
    CalendarOAuthStateStore,
    Depends(get_calendar_oauth_state_store),
]
OAuthProviders = Annotated[
    Mapping[CalendarProvider, CalendarOAuthProvider],
    Depends(get_calendar_oauth_providers),
]
CredentialVault = Annotated[
    CalendarCredentialVault,
    Depends(get_calendar_credential_vault),
]


def _redirect_uri_for_provider(
    request: Request,
    *,
    provider: CalendarProvider,
) -> str:
    """Return only a server-configured callback URI for the selected provider."""
    settings = cast(Settings, request.app.state.settings)

    redirect_uri = {
        CalendarProvider.GOOGLE: settings.calendar_google_oauth_redirect_uri,
        CalendarProvider.MICROSOFT: settings.calendar_microsoft_oauth_redirect_uri,
    }.get(provider)

    if redirect_uri is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Calendar authorization service is unavailable.",
            headers={
                "Retry-After": "5",
                "Cache-Control": "private, no-store",
            },
        )

    return str(redirect_uri)


@router.post(
    "/{provider}/authorization",
    response_model=CalendarAuthorizationUrlResponse,
    status_code=status.HTTP_200_OK,
    summary="Start calendar authorization",
)
async def begin_calendar_authorization_endpoint(
    provider: CalendarProvider,
    request: Request,
    response: Response,
    context: CallerContext,
    session: DatabaseSession,
    oauth_state_store: OAuthStateStore,
    oauth_providers: OAuthProviders,
) -> CalendarAuthorizationUrlResponse:
    """Create one authorization URL for the authenticated user's calendar."""
    authorization_url = await begin_calendar_authorization(
        session,
        context=context,
        provider=provider,
        redirect_uri=_redirect_uri_for_provider(
            request,
            provider=provider,
        ),
        oauth_state_store=oauth_state_store,
        oauth_providers=oauth_providers,
    )

    response.headers["Cache-Control"] = "private, no-store"

    return CalendarAuthorizationUrlResponse(
        authorization_url=authorization_url,
        expires_in_seconds=600,
    )


@router.get(
    "/{provider}/callback",
    response_model=CalendarConnectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete calendar authorization",
)
async def complete_calendar_authorization_endpoint(
    provider: CalendarProvider,
    request: Request,
    response: Response,
    code: Annotated[str, Query(min_length=1, max_length=4096)],
    state: Annotated[str, Query(min_length=32, max_length=512)],
    session: DatabaseSession,
    oauth_state_store: OAuthStateStore,
    oauth_providers: OAuthProviders,
    credential_vault: CredentialVault,
) -> CalendarConnectionResponse:
    """
    Complete a one-time provider callback.

    This endpoint intentionally does not require a bearer token: the opaque,
    short-lived OAuth state binds the callback to its original tenant and user.
    """
    connection = await complete_calendar_authorization(
        session,
        provider=provider,
        state_token=state,
        authorization_code=SecretStr(code),
        request_id=request.headers.get("X-Request-ID", "unknown"),
        oauth_state_store=oauth_state_store,
        oauth_providers=oauth_providers,
        credential_vault=credential_vault,
    )

    response.headers["Cache-Control"] = "private, no-store"
    return CalendarConnectionResponse.model_validate(connection)
