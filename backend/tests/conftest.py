"""Shared pytest fixtures for backend tests."""
import pytest_asyncio

from database import engine


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine():
    """Dispose the shared engine after each test so a fresh event loop
    gets fresh connections (pytest-asyncio uses a new loop per test)."""
    yield
    await engine.dispose()
