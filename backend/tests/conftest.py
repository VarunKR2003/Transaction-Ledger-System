"""
Test fixtures for async API testing.

Uses a separate test database with transaction rollback per test
for isolation. AsyncClient from httpx for making requests.
"""

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.rate_limiter import rate_limiter


# Use a separate test database URL
# Dynamically append '_test' to whatever database name is defined in settings.DATABASE_URL
db_url_parts = settings.DATABASE_URL.rsplit("/", 1)
if len(db_url_parts) == 2 and db_url_parts[1]:
    db_name_and_query = db_url_parts[1].split("?", 1)
    db_name = db_name_and_query[0]
    query = f"?{db_name_and_query[1]}" if len(db_name_and_query) == 2 else ""
    TEST_DATABASE_URL = f"{db_url_parts[0]}/{db_name}_test{query}"
else:
    TEST_DATABASE_URL = settings.DATABASE_URL + "_test"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

TestSessionFactory = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create all tables before tests, drop after."""
    # Ensure test database exists
    main_engine = create_async_engine(
        settings.DATABASE_URL,
        isolation_level="AUTOCOMMIT",
    )
    db_name = TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0]
    async with main_engine.connect() as conn:
        exists_result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": db_name},
        )
        if not exists_result.scalar():
            await conn.execute(text(f"CREATE DATABASE {db_name}"))
    await main_engine.dispose()

    # Create tables in test database
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    """Clean all table data between tests for isolation."""
    yield
    async with TestSessionFactory() as session:
        await session.execute(text("DELETE FROM transactions"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """Reset rate limiter state between tests."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Override the get_db dependency to use the test database."""
    async with TestSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for API testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Direct DB session for test setup/assertions."""
    async with TestSessionFactory() as session:
        yield session
