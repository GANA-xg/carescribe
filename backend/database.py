"""Database engine and session management.

Async SQLAlchemy with asyncpg. DATABASE_URL must use postgresql+asyncpg://.

The engine is bound lazily per-event-loop: pytest-asyncio gives each test
a fresh loop, so a module-global engine would leak connections across
loops ("Task attached to a different loop"). get_engine() rebuilds the
engine when the current loop changes.
"""
import os
import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://carescribe:carescribe@localhost:5432/carescribe")

_engine = None
_engine_loop_id: int | None = None
_sessionmaker: async_sessionmaker | None = None


def get_engine():
    """Return an engine bound to the current running event loop."""
    global _engine, _engine_loop_id, _sessionmaker
    try:
        loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        loop_id = None
    if _engine is None or _engine_loop_id != loop_id:
        _engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        _engine_loop_id = loop_id
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


class _SessionLocalProxy:
    """Attribute-transparent proxy so `SessionLocal()` always uses the
    sessionmaker bound to the current event loop."""

    def __call__(self, *args, **kwargs):
        get_engine()
        return _sessionmaker(*args, **kwargs)


SessionLocal = _SessionLocalProxy()


class Base(DeclarativeBase):
    """Declarative base for all CareScribe models."""


async def get_db():
    """FastAPI dependency that yields an async session."""
    async with SessionLocal() as session:
        yield session
