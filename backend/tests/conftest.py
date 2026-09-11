"""Shared test fixtures — engine teardown + face-test row cleanup."""
import pytest_asyncio
from sqlalchemy import delete, select

import database
from database import SessionLocal
from models.db import FaceEmbedding, Patient, User


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine():
    """Drop the loop-bound engine after each test so the next test's fresh
    event loop gets a fresh engine (per-loop binding in database.get_engine)."""
    yield
    if database._engine is not None:
        try:
            await database._engine.dispose()
        except Exception:
            pass
        database._engine = None
        database._sessionmaker = None
        database._engine_loop_id = None


@pytest_asyncio.fixture(autouse=True)
async def clean_test_face_rows():
    """Remove face embeddings enrolled by face tests so FAISS matches
    never leak between runs (tests hit the real dev DB)."""
    yield
    async with SessionLocal() as session:
        user_ids = (
            await session.execute(select(User.id).where(User.name.like("Face %")))
        ).scalars().all()
        if not user_ids:
            return
        patient_ids = (
            await session.execute(select(Patient.id).where(Patient.user_id.in_(user_ids)))
        ).scalars().all()
        if patient_ids:
            await session.execute(
                delete(FaceEmbedding).where(FaceEmbedding.patient_id.in_(patient_ids))
            )
            await session.commit()
