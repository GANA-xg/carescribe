"""CL-07 tests — doctor patient list. DB real, auth real."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from main import app
from database import SessionLocal
from models.db import Patient, User


async def _register(client: AsyncClient, role: str):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": f"{role.title()} User", "email": email, "password": "testpass123", "role": role},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]["id"]


async def _patient_row_for(user_id: str) -> str:
    async with SessionLocal() as session:
        p = await session.scalar(select(Patient).where(Patient.user_id == user_id))
    return p.id


@pytest.mark.asyncio
async def test_patients_requires_doctor():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, _ = await _register(client, "patient")
        r = await client.get("/patients", headers=headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_patients_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/patients")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_patients_lists_registered_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, patient_uid = await _register(client, "patient")
        doctor_headers, _ = await _register(client, "doctor")

        r = await client.get("/patients", headers=doctor_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "patients" in body

        # Match the exact patient we just registered (email is unique).
        patient_email = None
        async with SessionLocal() as session:
            u = await session.scalar(select(User).where(User.id == patient_uid))
            patient_email = u.email
        entry = next(p for p in body["patients"] if p["email"] == patient_email)
        assert entry["name"] == "Patient User"
        assert entry["id"] == str(await _patient_row_for(patient_uid))
        assert "last_visit" in entry
