"""Reusable HTTP helpers for idempotent write endpoints."""

from typing import Annotated

from fastapi import Depends
from fastapi.responses import JSONResponse

from app.api.dependencies import get_idempotency_key
from app.services.idempotency import IdempotencyResult

IdempotencyKey = Annotated[str, Depends(get_idempotency_key)]


def idempotency_response(result: IdempotencyResult) -> JSONResponse:
    """Return an idempotent operation result with replay visibility."""
    return JSONResponse(
        status_code=result.status_code,
        content=result.body,
        headers={
            "Idempotent-Replayed": str(result.replayed).lower(),
        },
    )
