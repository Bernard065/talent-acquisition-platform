"""Shared fixtures for database-backed tests."""

import os
from collections.abc import AsyncIterator
from importlib import import_module

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.base import Base

# Register all SQLAlchemy models with Base.metadata before creating the schema.
import_module("app.db.models")


def _get_test_database_url() -> str:
    """Return a test-only database URL and reject unsafe database names."""
    database_url = os.environ.get("TEST_DATABASE_URL")
    if database_url is None:
        configured_url = get_settings().database_url
        if configured_url is None:
            raise RuntimeError(
                "TEST_DATABASE_URL or DATABASE_URL must be configured for "
                "database-backed tests."
            )

        base_url = make_url(str(configured_url))
        if base_url.database is None:
            raise RuntimeError("DATABASE_URL must include a database name.")

        database_url = base_url.set(
            database=f"{base_url.database}_test",
            host="localhost",
        ).render_as_string(hide_password=False)

    database_name = make_url(database_url).database
    if database_name is None or not database_name.endswith("_test"):
        raise RuntimeError(
            "TEST_DATABASE_URL must use a database whose name ends in '_test'."
        )

    return database_url


@pytest_asyncio.fixture(scope="session", loop_scope="session", name="database_engine")
async def _database_engine_fixture() -> AsyncIterator[AsyncEngine]:
    """Create an isolated schema for this test session."""
    engine = create_async_engine(_get_test_database_url(), poolclass=NullPool)

    async with engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS btree_gist"))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database_before_test(
    request: pytest.FixtureRequest,
) -> AsyncIterator[None]:
    """Keep database-backed tests isolated from module-level teardown order."""
    if "database_engine" not in request.fixturenames:
        yield
        return

    engine = request.getfixturevalue("database_engine")
    table_names = ", ".join(
        f'"{table.name}"' for table in Base.metadata.sorted_tables
    )

    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE TABLE {table_names} CASCADE"))

    yield


@pytest_asyncio.fixture
async def session(database_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide one isolated asynchronous database session."""
    session_factory = async_sessionmaker(
        bind=database_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    async with session_factory() as database_session:
        try:
            yield database_session
        finally:
            await database_session.rollback()

    async with database_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "audit_events, requisitions, user_role_assignments, users, tenants "
                "CASCADE"
            )
        )
