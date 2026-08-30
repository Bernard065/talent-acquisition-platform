"""Database connection and lifecycle management."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


class Database:
    """Owns the database engine; domain code must not create its own engines."""

    def __init__(self, database_url: str) -> None:
        """Initialize the database engine with the provided URL."""
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    async def ping(self) -> None:
        """Verify that the database connection is available."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        """Dispose of the database engine and its connections."""
        await self.engine.dispose()
