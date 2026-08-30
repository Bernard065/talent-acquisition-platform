"""Application health check endpoints."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import Database

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Process is running. Safe for container orchestration probes."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(request: Request) -> dict[str, str]:
    """Service can reach its required transactional data store."""
    database: Database = request.app.state.database

    try:
        await database.ping()
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from error

    return {"status": "ok"}
