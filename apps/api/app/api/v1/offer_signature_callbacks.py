"""Public, HMAC-verified offer-signature provider callback endpoint."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_db_session,
    get_offer_signature_callback_verifiers,
)
from app.services.offer_signature_callback_provider import (
    OfferSignatureCallbackVerificationRequest,
    OfferSignatureCallbackVerifier,
)
from app.services.offer_signature_callbacks import (
    process_offer_signature_callback,
)
from app.services.offer_signature_errors import (
    OfferSignatureCallbackEnvelopeNotFoundError,
    OfferSignatureCallbackReplayMismatchError,
    OfferSignatureCallbackVerificationError,
)

router = APIRouter(
    prefix="/integrations/offer-signatures",
    tags=["Offer signature callbacks"],
)


DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CallbackVerifiers = Annotated[
    Mapping[str, OfferSignatureCallbackVerifier],
    Depends(get_offer_signature_callback_verifiers),
]


def _accepted_response() -> Response:
    """Return a generic acknowledgement for accepted or replayed callbacks."""
    return Response(
        status_code=status.HTTP_202_ACCEPTED,
        headers={"Cache-Control": "no-store"},
    )


def _normalise_provider(provider: str) -> str:
    """Validate a provider path value before selecting a configured verifier."""
    normalized = provider.strip().lower()

    if (
        not normalized
        or len(normalized) > 50
        or not normalized.replace("-", "").replace("_", "").isalnum()
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
            headers={"Cache-Control": "no-store"},
        )

    return normalized


async def _read_limited_body(
    request: Request,
    *,
    maximum_bytes: int,
) -> bytes:
    """Read raw callback bytes once while enforcing a strict body limit."""
    content_length = request.headers.get("Content-Length")

    if content_length is not None:
        try:
            if int(content_length) > maximum_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Callback body is too large.",
                    headers={"Cache-Control": "no-store"},
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Content-Length header.",
                headers={"Cache-Control": "no-store"},
            ) from None

    body = await request.body()

    if len(body) > maximum_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Callback body is too large.",
            headers={"Cache-Control": "no-store"},
        )

    return body


@router.post(
    "/{provider}/callbacks",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive an offer-signature provider callback",
)
async def receive_offer_signature_callback(
    provider: str,
    request: Request,
    session: DatabaseSession,
    verifiers: CallbackVerifiers,
) -> Response:
    """
    Verify and acknowledge one provider callback.

    No JWT is accepted or required. The verifier authenticates the provider
    from the exact raw request body and provider signature headers.
    """
    normalized_provider = _normalise_provider(provider)
    verifier = verifiers.get(normalized_provider)

    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found.",
            headers={"Cache-Control": "no-store"},
        )

    maximum_bytes = request.app.state.settings.offer_signature_callback_max_body_bytes
    raw_body = await _read_limited_body(
        request,
        maximum_bytes=maximum_bytes,
    )

    try:
        await process_offer_signature_callback(
            session,
            provider=normalized_provider,
            verifier=verifier,
            verification_request=OfferSignatureCallbackVerificationRequest(
                raw_body=raw_body,
                headers=dict(request.headers),
                received_at=datetime.now(UTC),
            ),
            request_id=request.headers.get("X-Request-ID", "unknown"),
        )
    except (
        OfferSignatureCallbackVerificationError,
        OfferSignatureCallbackEnvelopeNotFoundError,
        OfferSignatureCallbackReplayMismatchError,
    ):
        # Do not reveal signature, envelope, tenant, replay, or provider-state
        # information. Providers receive a non-retryable generic response.
        return _accepted_response()

    return _accepted_response()
