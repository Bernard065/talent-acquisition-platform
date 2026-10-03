"""Authentication tests for verified Auth0 Organization tenant resolution."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
import structlog
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.dependencies import get_tenant_context
from app.core.authorization import Role
from app.core.config import Settings
from app.core.security import JwtVerifier, TokenClaims
from app.db.models.identity import Tenant


def _settings() -> Settings:
    """Build minimal Auth0-compatible settings for signed-token tests."""
    return Settings(
        app_env="test",
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
    )


def _signed_token(
    monkeypatch: pytest.MonkeyPatch,
    *,
    claims: dict[str, object],
) -> tuple[JwtVerifier, str]:
    """Create an RS256 token while replacing remote JWKS access with a key."""
    settings = _settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    verifier = JwtVerifier(settings)
    monkeypatch.setattr(
        verifier._jwks_client,
        "get_signing_key_from_jwt",
        lambda _token: SimpleNamespace(key=public_key),
    )

    issued_at = int(datetime.now(UTC).timestamp())
    payload: dict[str, object] = {
        "iss": str(settings.jwt_issuer),
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "exp": issued_at + 300,
        "sub": "auth0|candidate-recruiter",
        **claims,
    }
    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    return verifier, token


def test_verifier_uses_signed_auth0_org_claim_and_ignores_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A verified Auth0 org_id is accepted; a token tenant_id is not trusted."""
    verifier, token = _signed_token(
        monkeypatch,
        claims={
            "org_id": "org_verified",
            "tenant_id": str(uuid4()),
            "roles": [Role.RECRUITER.value],
        },
    )

    claims = verifier.verify(token)

    assert claims.org_id == "org_verified"
    assert claims.sub == "auth0|candidate-recruiter"
    assert claims.roles == {Role.RECRUITER}
    assert "tenant_id" not in claims.model_dump()


def test_verifier_rejects_legacy_token_without_auth0_org_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signed tenant_id alone cannot establish an authenticated tenant."""
    verifier, token = _signed_token(
        monkeypatch,
        claims={"tenant_id": str(uuid4())},
    )

    with pytest.raises(InvalidTokenError, match="invalid access token"):
        verifier.verify(token)


def _request() -> Request:
    """Build a minimal request carrying a request ID for the dependency."""
    return Request(
        {
            "type": "http",
            "headers": [(b"x-request-id", b"auth0-tenant-resolution-test")],
        }
    )


async def test_tenant_context_resolves_only_from_auth0_org_mapping(
    session: AsyncSession,
) -> None:
    """A forged token tenant_id cannot override the organization mapping."""
    mapped_tenant = Tenant(
        name="Mapped tenant",
        slug=f"mapped-{uuid4().hex[:12]}",
        auth0_organization_id="org_context_mapping_test",
    )
    forged_tenant = Tenant(
        name="Unrelated tenant",
        slug=f"unrelated-{uuid4().hex[:12]}",
    )
    session.add_all([mapped_tenant, forged_tenant])
    await session.flush()
    claims = TokenClaims.model_validate(
        {
            "sub": "auth0|candidate-recruiter",
            "org_id": "org_context_mapping_test",
            "tenant_id": str(forged_tenant.id),
            "roles": [Role.RECRUITER.value],
        }
    )

    try:
        context = await get_tenant_context(_request(), claims, session)
    finally:
        structlog.contextvars.clear_contextvars()

    assert context.tenant_id == mapped_tenant.id
    assert context.tenant_id != forged_tenant.id
    assert context.roles == frozenset({Role.RECRUITER})


async def test_unmapped_auth0_organization_is_forbidden(
    session: AsyncSession,
) -> None:
    """A valid token from an unprovisioned organization fails closed."""
    claims = TokenClaims(
        sub="auth0|unmapped-user",
        org_id="org_not_provisioned",
    )

    with pytest.raises(HTTPException) as error:
        await get_tenant_context(_request(), claims, session)

    structlog.contextvars.clear_contextvars()
    assert error.value.status_code == 403
    assert error.value.detail == "Insufficient permission."
