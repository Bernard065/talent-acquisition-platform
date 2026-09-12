"""Unit tests for calendar OAuth PKCE and redirect validation."""

from pydantic import SecretStr

from app.services.calendar_connections import (
    _pkce_challenge,
    _validate_redirect_uri,
)


def test_derives_rfc7636_s256_pkce_challenge() -> None:
    """Use the standard RFC 7636 verifier/challenge example."""
    verifier = SecretStr(
        "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    )

    assert _pkce_challenge(verifier) == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_accepts_https_and_local_development_redirect_uris() -> None:
    """Allow trusted HTTPS callbacks and localhost development callbacks."""
    assert _validate_redirect_uri("https://app.example.test/oauth/callback") == (
        "https://app.example.test/oauth/callback"
    )
    assert _validate_redirect_uri("http://localhost:3000/oauth/callback") == (
        "http://localhost:3000/oauth/callback"
    )
