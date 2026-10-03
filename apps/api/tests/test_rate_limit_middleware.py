"""HTTP integration tests for route-aware rate-limit enforcement."""

from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jwt import InvalidTokenError
from prometheus_client import REGISTRY

from app.core.authorization import Role, TenantContext
from app.core.config import Settings
from app.core.security import JwtVerifier, TokenClaims
from app.main import create_app
from app.observability.metrics import RATE_LIMIT_REQUESTS
from app.services.rate_limiting import (
    RateLimitPolicy,
    RateLimitResult,
    RateLimitUnavailableError,
)

_PUBLIC_APPLICATION_PATH = (
    "/api/v1/public/jobs/"
    "00000000-0000-0000-0000-000000000001/applications"
)
_SIGNATURE_CALLBACK_PATH = (
    "/api/v1/integrations/offer-signatures/local/callbacks"
)


class _FakeJwtVerifier(JwtVerifier):
    """Return a controlled verified tenant identity without JWKS access."""

    def __init__(self, context: TenantContext) -> None:
        """Initialize the fake verifier and satisfy the base-class contract."""
        super().__init__(_settings())
        self._context = context

    def verify(self, token: str) -> TokenClaims:
        """Validate a fixed test token and return configured Auth0 claims."""
        if token != "valid-test-token":  # noqa: S105
            raise InvalidTokenError("invalid token")

        return TokenClaims(
            sub=self._context.subject,
            org_id=f"org_{self._context.tenant_id.hex}",
            roles=set(self._context.roles),
        )


class _FakeRateLimiter:
    """Record middleware calls and return a configured rate-limit outcome."""

    def __init__(
        self,
        *,
        result: RateLimitResult | None = None,
        unavailable: bool = False,
    ) -> None:
        self.result = result or RateLimitResult(
            allowed=True,
            limit=300,
            remaining=299,
            retry_after_seconds=None,
        )
        self.unavailable = unavailable
        self.calls: list[tuple[str, RateLimitPolicy]] = []

    async def consume(
        self,
        *,
        key: str,
        policy: RateLimitPolicy,
    ) -> RateLimitResult:
        """Record the call and return the configured limiter outcome."""
        self.calls.append((key, policy))
        if self.unavailable:
            raise RateLimitUnavailableError("test Redis outage")
        return self.result


def _settings(*, trusted_proxy_cidrs: list[str] | None = None) -> Settings:
    return Settings(
        app_env="local",
        app_name="tap-api",
        app_version="0.1.0",
        api_prefix="/api/v1",
        log_level="INFO",
        redis_url="redis://localhost:6379/0",
        jwt_issuer="https://issuer.example.test/",
        jwt_audience="talent-acquisition-api",
        jwt_jwks_url="https://issuer.example.test/.well-known/jwks.json",
        jwt_algorithm="RS256",
        jwt_leeway_seconds=30,
        trusted_proxy_cidrs=trusted_proxy_cidrs or [],
    )


def _app(
    limiter: _FakeRateLimiter,
    *,
    trusted_proxy_cidrs: list[str] | None = None,
    context: TenantContext | None = None,
) -> FastAPI:
    application = create_app(
        _settings(trusted_proxy_cidrs=trusted_proxy_cidrs)
    )
    application.state.rate_limiter = limiter
    application.state.jwt_verifier = _FakeJwtVerifier(
        context
        or TenantContext(
            tenant_id=uuid4(),
            subject="recruiter-subject",
            roles=frozenset({Role.RECRUITER}),
            request_id="test-request",
        )
    )

    async def ok() -> dict[str, bool]:
        return {"ok": True}

    # These lightweight routes exercise private-route policy without requiring
    # database fixtures or endpoint-specific authorization dependencies.
    application.add_api_route("/api/v1/test/one", ok, methods=["GET"])
    application.add_api_route("/api/v1/test/two", ok, methods=["GET"])
    return application


async def _request(
    application: FastAPI,
    method: str,
    path: str,
    *,
    client: tuple[str, int] = ("198.51.100.8", 41000),
    headers: dict[str, str] | None = None,
) -> object:
    async with AsyncClient(
        transport=ASGITransport(app=application, client=client),
        base_url="http://testserver",
    ) as http_client:
        return await http_client.request(method, path, headers=headers)


@pytest.mark.asyncio
async def test_private_keys_are_scoped_to_verified_identity_and_route() -> None:
    """Private limits use verified tenant/subject and a stable route template."""
    tenant_id = uuid4()
    limiter = _FakeRateLimiter()
    application = _app(
        limiter,
        context=TenantContext(
            tenant_id=tenant_id,
            subject="recruiter-42",
            roles=frozenset({Role.RECRUITER}),
            request_id="request",
        ),
    )
    headers = {"Authorization": "Bearer valid-test-token"}

    first = await _request(
        application,
        "GET",
        "/api/v1/test/one",
        headers=headers,
    )
    second = await _request(
        application,
        "GET",
        "/api/v1/test/two",
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(limiter.calls) == 2
    assert limiter.calls[0][1] == RateLimitPolicy(limit=300, window_seconds=60)
    assert limiter.calls[0][0] != limiter.calls[1][0]
    assert str(tenant_id) not in limiter.calls[0][0]
    assert "recruiter-42" not in limiter.calls[0][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("different_tenant", "different_subject"),
    [(False, True), (True, False)],
    ids=["different-subject", "different-tenant"],
)
async def test_private_rate_limit_keys_are_isolated_by_identity(
    different_tenant: bool,
    different_subject: bool,
) -> None:
    """Authenticated callers in distinct scopes do not share a bucket."""
    tenant_id = uuid4()
    subject = "same-recruiter"
    other_tenant_id = uuid4() if different_tenant else tenant_id
    other_subject = "another-recruiter" if different_subject else subject

    limiter = _FakeRateLimiter()
    first_app = _app(
        limiter,
        context=TenantContext(
            tenant_id=tenant_id,
            subject=subject,
            roles=frozenset({Role.RECRUITER}),
            request_id="first-request",
        ),
    )
    second_app = _app(
        limiter,
        context=TenantContext(
            tenant_id=other_tenant_id,
            subject=other_subject,
            roles=frozenset({Role.RECRUITER}),
            request_id="second-request",
        ),
    )
    headers = {"Authorization": "Bearer valid-test-token"}

    first = await _request(
        first_app,
        "GET",
        "/api/v1/test/one",
        headers=headers,
    )
    second = await _request(
        second_app,
        "GET",
        "/api/v1/test/one",
        headers=headers,
    )

    assert first.status_code == second.status_code == 200
    assert len(limiter.calls) == 2
    assert limiter.calls[0][0] != limiter.calls[1][0]

    keys = " ".join(key for key, _ in limiter.calls)
    assert str(tenant_id) not in keys
    assert subject not in keys
    assert other_subject not in keys


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "expected_policy"),
    [
        (
            "POST",
            _PUBLIC_APPLICATION_PATH,
            RateLimitPolicy(limit=5, window_seconds=900),
        ),
        (
            "POST",
            _SIGNATURE_CALLBACK_PATH,
            RateLimitPolicy(limit=120, window_seconds=60),
        ),
    ],
)
async def test_sensitive_anonymous_routes_use_their_own_policies(
    method: str,
    path: str,
    expected_policy: RateLimitPolicy,
) -> None:
    """Public submissions and provider callbacks receive distinct limits."""
    limiter = _FakeRateLimiter(
        result=RateLimitResult(
            allowed=False,
            limit=expected_policy.limit,
            remaining=0,
            retry_after_seconds=17,
        )
    )
    application = _app(limiter)

    response = await _request(application, method, path)

    assert response.status_code == 429
    assert limiter.calls[0][1] == expected_policy
    assert response.headers["Retry-After"] == "17"
    assert response.headers["Cache-Control"] == "no-store"


def _rate_limit_metric_value(route_category: str, outcome: str) -> float:
    """Read one bounded counter series for before/after assertions."""
    return REGISTRY.get_sample_value(
        "tap_rate_limit_requests_total",
        {"route_category": route_category, "outcome": outcome},
    ) or 0.0


@pytest.mark.asyncio
async def test_rate_limit_outcomes_are_exported_without_identity_labels() -> None:
    """Allow, reject, and outage outcomes increment bounded metric series."""
    allowed_before = _rate_limit_metric_value("public-read", "allowed")
    limited_before = _rate_limit_metric_value(
        "public-application",
        "limited",
    )
    unavailable_before = _rate_limit_metric_value(
        "signature-callback",
        "unavailable",
    )

    allowed_limiter = _FakeRateLimiter()
    allowed_response = await _request(
        _app(allowed_limiter),
        "GET",
        "/api/v1/public/jobs",
    )
    limited_limiter = _FakeRateLimiter(
        result=RateLimitResult(
            allowed=False,
            limit=5,
            remaining=0,
            retry_after_seconds=12,
        )
    )
    limited_response = await _request(
        _app(limited_limiter),
        "POST",
        _PUBLIC_APPLICATION_PATH,
    )
    unavailable_limiter = _FakeRateLimiter(unavailable=True)
    unavailable_response = await _request(
        _app(unavailable_limiter),
        "POST",
        _SIGNATURE_CALLBACK_PATH,
    )

    assert allowed_response.status_code == 503  # endpoint DB is not initialized
    assert limited_response.status_code == 429
    assert unavailable_response.status_code == 503
    assert _rate_limit_metric_value("public-read", "allowed") == allowed_before + 1
    assert (
        _rate_limit_metric_value("public-application", "limited")
        == limited_before + 1
    )
    assert (
        _rate_limit_metric_value("signature-callback", "unavailable")
        == unavailable_before + 1
    )

    assert RATE_LIMIT_REQUESTS._labelnames == ("route_category", "outcome")
    assert all(
        set(sample.labels) == {"route_category", "outcome"}
        for metric in RATE_LIMIT_REQUESTS.collect()
        for sample in metric.samples
    )


@pytest.mark.asyncio
async def test_public_job_reads_use_the_public_read_policy() -> None:
    """Anonymous job discovery uses its own rate-limit category."""
    limiter = _FakeRateLimiter()
    application = _app(limiter)

    response = await _request(application, "GET", "/api/v1/public/jobs")

    # The request passes rate limiting and reaches the database dependency.
    assert response.status_code == 503
    assert len(limiter.calls) == 1
    assert limiter.calls[0][1] == RateLimitPolicy(limit=120, window_seconds=60)


@pytest.mark.asyncio
async def test_rejected_request_has_generic_no_store_response() -> None:
    """A rate-limited response does not disclose identity or route data."""
    limiter = _FakeRateLimiter(
        result=RateLimitResult(
            allowed=False,
            limit=300,
            remaining=0,
            retry_after_seconds=9,
        )
    )
    application = _app(limiter)

    response = await _request(
        application,
        "GET",
        "/api/v1/test/one",
        headers={"Authorization": "Bearer valid-test-token"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too many requests."
    assert response.headers["Retry-After"] == "9"
    assert response.headers["RateLimit-Limit"] == "300"
    assert response.headers["RateLimit-Remaining"] == "0"
    assert response.headers["Cache-Control"] == "no-store"
    assert "recruiter-subject" not in response.text


@pytest.mark.asyncio
async def test_public_application_and_callback_fail_closed_on_redis_outage() -> None:
    """Sensitive anonymous routes return a generic 503 during Redis failure."""
    for path in (_PUBLIC_APPLICATION_PATH, _SIGNATURE_CALLBACK_PATH):
        limiter = _FakeRateLimiter(unavailable=True)
        application = _app(limiter)

        response = await _request(application, "POST", path)

        assert response.status_code == 503
        assert response.json()["detail"] == (
            "Request protection is temporarily unavailable."
        )
        assert response.headers["Retry-After"] == "5"
        assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.asyncio
async def test_other_routes_fail_open_on_redis_outage() -> None:
    """Non-sensitive route handling continues during a rate-limit outage."""
    limiter = _FakeRateLimiter(unavailable=True)
    application = _app(limiter)

    private_response = await _request(
        application,
        "GET",
        "/api/v1/test/one",
        headers={"Authorization": "Bearer valid-test-token"},
    )
    public_response = await _request(
        application,
        "GET",
        "/api/v1/public/jobs",
    )

    assert private_response.status_code == 200
    # Public job discovery proceeds past the limiter and reaches the database
    # dependency, which is intentionally not initialized in this test app.
    assert public_response.status_code == 503
    assert public_response.json()["detail"] == "Database service is unavailable."


@pytest.mark.asyncio
async def test_forwarded_ip_is_used_only_from_a_trusted_proxy() -> None:
    """Untrusted clients cannot choose their rate-limit identity via XFF."""
    limiter = _FakeRateLimiter()
    application = _app(
        limiter,
        trusted_proxy_cidrs=["10.0.0.0/8"],
    )

    await _request(
        application,
        "GET",
        "/api/v1/public/jobs",
        client=("10.0.0.5", 41000),
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    await _request(
        application,
        "GET",
        "/api/v1/public/jobs",
        client=("10.0.0.5", 41000),
        headers={"X-Forwarded-For": "203.0.113.11"},
    )
    await _request(
        application,
        "GET",
        "/api/v1/public/jobs",
        client=("198.51.100.8", 41000),
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    await _request(
        application,
        "GET",
        "/api/v1/public/jobs",
        client=("198.51.100.8", 41000),
        headers={"X-Forwarded-For": "203.0.113.11"},
    )

    trusted_proxy_keys = [limiter.calls[0][0], limiter.calls[1][0]]
    untrusted_peer_keys = [limiter.calls[2][0], limiter.calls[3][0]]

    assert trusted_proxy_keys[0] != trusted_proxy_keys[1]
    assert untrusted_peer_keys[0] == untrusted_peer_keys[1]
