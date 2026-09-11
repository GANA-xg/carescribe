"""OC-02 smoke test — schema integrity against the live dev Postgres.

Run inside backend container:
    pytest tests/test_db_schema.py -v

Requires the stack up (postgres) and migrations applied.
"""
import datetime
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import SessionLocal
from models.db import ChatHistory, Doctor, FaceEmbedding, HealthRecord, Patient, Prescription, User


@pytest.mark.asyncio
async def test_tables_exist_and_seed_present():
    """Seed users exist and relationships resolve (eager loaded)."""
    async with SessionLocal() as session:
        patient_user = (
            await session.execute(
                select(User)
                .where(User.email == "patient@carescribe.test")
                .options(selectinload(User.patient))
            )
        ).scalar_one()
        doctor_user = (
            await session.execute(
                select(User)
                .where(User.email == "doctor@carescribe.test")
                .options(selectinload(User.doctor))
            )
        ).scalar_one()

        assert patient_user.role == "patient" and patient_user.patient is not None
        assert doctor_user.role == "doctor" and doctor_user.doctor is not None
        assert doctor_user.doctor.specialization == "Internal Medicine"


@pytest.mark.asyncio
async def test_full_crud_roundtrip():
    """Insert one row per table, verify, then roll back (leaves DB clean)."""
    async with SessionLocal() as session:
        patient = Patient(
            user=User(
                name="Crud Roundtrip",
                email=f"crud-{uuid.uuid4().hex[:8]}@test",
                password_hash="x",
                role="patient",
            )
        )
        session.add(patient)
        await session.flush()

        rx = Prescription(patient=patient, ocr_job_id="job-123", raw_text="Rx test", structured_data={"drugs": []})
        rec = HealthRecord(patient=patient, type="lab", data={"hba1c": 5.4}, source="manual")
        chat = ChatHistory(patient=patient, role="user", content="hello")
        emb = FaceEmbedding(patient=patient, embedding=b"\x00" * 16, model_name="test")
        session.add_all([rx, rec, chat, emb])
        await session.flush()

        assert rx.id and rec.id and chat.id and emb.id
        assert isinstance(rec.created_at, datetime.datetime)

        await session.rollback()  # keep the dev DB clean
