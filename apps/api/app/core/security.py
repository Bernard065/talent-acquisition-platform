"""JWT authentication and security utilities."""

from typing import Any
from uuid import UUID

import jwt
from jwt import InvalidTokenError, PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.authorization import Role, TenantContext
from app.core.config import Settings


class TokenClaims(BaseModel):
    """Claims contract agreed with the external identity provider."""

    model_config = ConfigDict(extra="ignore")

    sub: str = Field(min_length=1)
    tenant_id: UUID
    roles: set[Role] = Field(default_factory=set)


class JwtVerifier:
    """Verifies RS256 access tokens against the configured JWKS endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = PyJWKClient(str(settings.jwt_jwks_url))

    def verify(self, token: str, request_id: str) -> TenantContext:
        """Verify an access token and return its authenticated tenant context."""
        try:
            header: dict[str, Any] = jwt.get_unverified_header(token)

            # Never trust a token-selected algorithm.
            if header.get("alg") != self._settings.jwt_algorithm:
                raise InvalidTokenError("unexpected signing algorithm")

            signing_key = self._jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[self._settings.jwt_algorithm],
                audience=self._settings.jwt_audience,
                issuer=str(self._settings.jwt_issuer),
                leeway=self._settings.jwt_leeway_seconds,
                options={
                    "require": ["exp", "iat", "iss", "aud", "sub", "tenant_id"],
                },
            )

            claims = TokenClaims.model_validate(payload)

        except (InvalidTokenError, ValidationError) as error:
            raise InvalidTokenError("invalid access token") from error

        return TenantContext(
            tenant_id=claims.tenant_id,
            subject=claims.sub,
            roles=frozenset(claims.roles),
            request_id=request_id,
        )
