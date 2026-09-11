"""Database engine and session management.

Async SQLAlchemy with asyncpg. The DATABASE_URL env var must use the
postgresql+asyncpg:// scheme. pgvector extension is created by the first
migration (needed for RAG embeddings in OC-12).
"""
import os

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://carescribe:carescribe@localhost:5432/carescribe")

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base for all CareScribe models."""


async def get_db():
    """FastAPI dependency that yields an async session."""
    async with SessionLocal() as session:
        yield session
