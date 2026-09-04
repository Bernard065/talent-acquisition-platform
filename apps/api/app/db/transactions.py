"""Transaction helpers for composable application services."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def transactional(session: AsyncSession) -> AsyncGenerator[None, None]:
    """Run work atomically, joining an existing unit of work when present."""
    if session.in_transaction():
        async with session.begin_nested():
            yield
    else:
        async with session.begin():
            yield
