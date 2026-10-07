"""JWT authentication and security utilities."""

from typing import Any

import jwt
from jwt import InvalidTokenError, PyJWKClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.authorization import Role
from app.core.config import Settings


class TokenClaims(BaseModel):
    """Verified identity claims accepted from the configured OIDC provider."""

    model_config = ConfigDict(extra="ignore")

    sub: str = Field(min_length=1)
    org_id: str = Field(min_length=1, max_length=255)
    roles: set[Role] = Field(default_factory=set)

    @model_validator(mode="before")
    @classmethod
    def read_supabase_app_metadata(cls, value: Any) -> Any:
        """Use trusted Supabase app_metadata when direct API claims are absent.

        Supabase places administrator-managed user metadata under the signed
        ``app_metadata`` claim. The workspace bootstrap stores the provider
        organization ID and roles there, while other OIDC providers may issue
        the API's canonical ``org_id`` and ``roles`` claims directly.
        """
        if not isinstance(value, dict):
            return value

        app_metadata = value.get("app_metadata")
        if not isinstance(app_metadata, dict):
            return value

        normalized = dict(value)
        if "org_id" not in normalized:
            organization_id = app_metadata.get("organization_id")
            if isinstance(organization_id, str):
                normalized["org_id"] = organization_id
        if "roles" not in normalized:
            roles = app_metadata.get("roles")
            if isinstance(roles, list):
                normalized["roles"] = roles
        return normalized


class JwtVerifier:
    """Verifies configured access tokens against the identity provider JWKS."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwks_client = PyJWKClient(str(settings.jwt_jwks_url))

    def verify(self, token: str) -> TokenClaims:
        """Verify an access token and return its validated identity claims."""
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
                    "require": ["exp", "iat", "iss", "aud", "sub"],
                },
            )

            claims = TokenClaims.model_validate(payload)

        except (InvalidTokenError, ValidationError) as error:
            raise InvalidTokenError("invalid access token") from error

        return claims
