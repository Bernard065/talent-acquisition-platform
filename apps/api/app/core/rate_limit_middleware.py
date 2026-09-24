"""Route-aware request rate-limit enforcement."""

from __future__ import annotations

import hashlib
import ipaddress
from typing import cast

import structlog
from fastapi import Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from jwt import InvalidTokenError
from starlette.routing import Match

from app.core.config import Settings
from app.core.security import JwtVerifier
from app.services.rate_limiting import (
    RateLimiter,
    RateLimitPolicy,
    RateLimitUnavailableError,
)

_HEALTH_ROUTE_SUFFIXES = ("/health/live", "/health/ready")
_PUBLIC_APPLICATION_SUFFIX = "/public/jobs/{public_job_id}/applications"
_SIGNATURE_CALLBACK_SUFFIX = (
    "/integrations/offer-signatures/{provider}/callbacks"
)
logger = structlog.get_logger()


def _matched_route(request: Request, api_prefix: str) -> str:
    """Resolve sensitive public routes before falling back to Starlette matching."""
    prefix = api_prefix.rstrip("/")
    path = request.url.path.rstrip("/")
    relative_path = path.removeprefix(prefix).strip("/")
    segments = relative_path.split("/") if relative_path else []

    if (
        request.method == "POST"
        and len(segments) == 4
        and segments[:2] == ["public", "jobs"]
        and segments[3] == "applications"
    ):
        return f"{prefix}/public/jobs/{{public_job_id}}/applications"

    if (
        request.method == "POST"
        and len(segments) == 4
        and segments[:2] == ["integrations", "offer-signatures"]
        and segments[3] == "callbacks"
    ):
        return f"{prefix}/integrations/offer-signatures/{{provider}}/callbacks"

    if (
        request.method == "GET"
        and segments[:2] == ["public", "jobs"]
        and len(segments) in (2, 3)
    ):
        return f"{prefix}/public/jobs"

    for route in request.app.router.routes:
        route_match, _ = route.matches(request.scope)
        if route_match is Match.FULL:
            route_path = getattr(route, "path", None)
            if isinstance(route_path, str):
                return route_path

    return "unmatched"


def _trusted_proxy_networks(settings: Settings) -> tuple[
    ipaddress.IPv4Network | ipaddress.IPv6Network, ...
]:
    """Parse proxy networks validated by settings construction."""
    return tuple(
        ipaddress.ip_network(value, strict=False)
        for value in settings.trusted_proxy_cidrs
    )


def _is_trusted(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...],
) -> bool:
    return any(
        address.version == network.version and address in network
        for network in networks
    )


def _client_address(request: Request, settings: Settings) -> str:
    """Use the socket peer unless it is an explicitly trusted proxy."""
    peer = request.client.host if request.client is not None else "unknown"

    try:
        peer_address = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"

    networks = _trusted_proxy_networks(settings)
    if not _is_trusted(peer_address, networks):
        return str(peer_address)

    forwarded_for = request.headers.get("X-Forwarded-For")
    if not forwarded_for:
        return str(peer_address)

    try:
        forwarded_addresses = [
            ipaddress.ip_address(value.strip())
            for value in forwarded_for.split(",")
        ]
    except ValueError:
        # A malformed forwarding chain is ignored; it never becomes identity.
        return str(peer_address)

    current_address: ipaddress.IPv4Address | ipaddress.IPv6Address = peer_address
    for forwarded_address in reversed(forwarded_addresses):
        if not _is_trusted(current_address, networks):
            break
        current_address = forwarded_address

    return str(current_address)


def _route_policy(
    *,
    route_template: str,
    settings: Settings,
) -> tuple[str, RateLimitPolicy, bool]:
    """Resolve a finite route category, policy, and fail-closed behavior."""
    api_prefix = settings.api_prefix.rstrip("/")

    if route_template.endswith(_PUBLIC_APPLICATION_SUFFIX):
        return (
            "public-application",
            RateLimitPolicy(
                limit=settings.rate_limit_public_applications,
                window_seconds=(
                    settings.rate_limit_public_application_window_seconds
                ),
            ),
            True,
        )

    if route_template.endswith(_SIGNATURE_CALLBACK_SUFFIX):
        return (
            "signature-callback",
            RateLimitPolicy(
                limit=settings.rate_limit_signature_callbacks,
                window_seconds=(
                    settings.rate_limit_signature_callback_window_seconds
                ),
            ),
            True,
        )

    if route_template.startswith(f"{api_prefix}/public/jobs"):
        return (
            "public-read",
            RateLimitPolicy(
                limit=settings.rate_limit_public_reads,
                window_seconds=settings.rate_limit_public_read_window_seconds,
            ),
            False,
        )

    if route_template == "unmatched" or not route_template.startswith(api_prefix):
        return (
            "anonymous",
            RateLimitPolicy(
                limit=settings.rate_limit_anonymous_requests,
                window_seconds=settings.rate_limit_anonymous_window_seconds,
            ),
            False,
        )

    return (
        "authenticated",
        RateLimitPolicy(
            limit=settings.rate_limit_authenticated_requests,
            window_seconds=settings.rate_limit_authenticated_window_seconds,
        ),
        False,
    )


async def enforce_request_rate_limit(request: Request) -> Response | None:
    """Consume the route's rate-limit token or return a safe error response."""
    settings = cast(Settings, request.app.state.settings)
    if (
        not settings.rate_limiting_enabled
        or request.method == "OPTIONS"
    ):
        return None

    route_template = _matched_route(request, settings.api_prefix)
    if route_template.endswith(_HEALTH_ROUTE_SUFFIXES):
        return None
    if route_template.endswith(("/docs", "/openapi.json")):
        return None

    category, policy, fail_closed = _route_policy(
        route_template=route_template,
        settings=settings,
    )

    limiter = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        # Unit/API test apps often omit the lifespan and inject dependencies
        # directly. A test can set a fake limiter to exercise this middleware.
        if settings.app_env == "test":
            return None
        if not fail_closed:
            return None

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Request protection is temporarily unavailable.",
                "request_id": request.headers.get("X-Request-ID", "unknown"),
            },
            headers={
                "Cache-Control": "no-store",
                "Retry-After": "5",
            },
        )

    client_address = _client_address(request, settings)
    key_identity = f"ip:{client_address}"

    if category == "authenticated":
        authorization = request.headers.get("Authorization", "")
        scheme, separator, token = authorization.partition(" ")
        if separator and scheme.lower() == "bearer" and token.strip():
            verifier = getattr(request.app.state, "jwt_verifier", None)
            if isinstance(verifier, JwtVerifier):
                request_id = request.headers.get("X-Request-ID", "unknown")
                try:
                    tenant_context = await run_in_threadpool(
                        verifier.verify,
                        token.strip(),
                        request_id,
                    )
                except InvalidTokenError:
                    # Keep invalid-token attempts under an IP bucket. The
                    # authentication dependency still returns the 401.
                    key_identity = f"invalid-auth:{client_address}"
                else:
                    request.state.verified_tenant_context = tenant_context
                    key_identity = (
                        f"tenant:{tenant_context.tenant_id}"
                        f":subject:{tenant_context.subject}"
                    )
        else:
            key_identity = f"unauthenticated:{client_address}"

    route_key = f"{request.method.upper()}:{route_template}"
    scoped_key = hashlib.sha256(
        f"{category}\0{key_identity}\0{route_key}".encode()
    ).hexdigest()

    try:
        result = await cast(RateLimiter, limiter).consume(
            key=f"{category}:{scoped_key}",
            policy=policy,
        )
    except RateLimitUnavailableError:
        if not fail_closed:
            logger.warning(
                "rate_limit_provider_unavailable_fail_open",
                route_category=category,
            )
            return None

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "detail": "Request protection is temporarily unavailable.",
                "request_id": request.headers.get("X-Request-ID", "unknown"),
            },
            headers={
                "Cache-Control": "no-store",
                "Retry-After": "5",
            },
        )

    if result.allowed:
        return None

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Too many requests.",
            "request_id": request.headers.get("X-Request-ID", "unknown"),
        },
        headers={
            "Cache-Control": "no-store",
            "Retry-After": str(result.retry_after_seconds or 1),
            "RateLimit-Limit": str(result.limit),
            "RateLimit-Remaining": "0",
        },
    )
