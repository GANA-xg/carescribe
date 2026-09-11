"""OC-08 tests — Health Passport. OpenEMR mocked; DB real."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from main import app
from routes import passport as passport_route
from database import SessionLocal
from models.db import Patient


async def _register_patient(client: AsyncClient):
    email = f"pass-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": "Passport User", "email": email, "password": "testpass123", "role": "patient"},
    )
    token = r.json()["token"]
    async with SessionLocal() as session:
        from models.db import User

        u = await session.scalar(select(User).where(User.email == email))
        p = await session.scalar(select(Patient).where(Patient.user_id == u.id))
    return {"Authorization": f"Bearer {token}"}, p.id


@pytest.fixture(autouse=True)
def mock_openemr(monkeypatch):
    async def fake_records(openemr_id):
        return [
            {"resourceType": "Condition", "code": {"text": "Type 2 Diabetes"}},
            {"resourceType": "MedicationRequest", "medicationCodeableConcept": {"text": "Metformin"}},
        ]

    monkeypatch.setattr(passport_route.openemr, "get_patient_records", fake_records)


@pytest.mark.asyncio
async def test_add_and_get_passport():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, pid = await _register_patient(client)

        # add two records
        r = await client.post(f"/passport/{pid}/records", headers=headers,
                              json={"type": "prescription",
                                    "data": {"drugs": [{"name": "Amoxicillin"}]},
                                    "source": "ocr"})
        assert r.status_code == 201, r.text
        rid = r.json()["record"]["id"]

        r = await client.post(f"/passport/{pid}/records", headers=headers,
                              json={"type": "diagnosis",
                                    "data": {"diagnosis": "URTI"},
                                    "source": "manual"})
        assert r.status_code == 201

        # full passport view
        r = await client.get(f"/passport/{pid}", headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["summary"]["total"] == 2
        assert "Amoxicillin" in body["summary"]["medications"]
        assert "URTI" in body["summary"]["conditions"]
        assert body["summary"]["last_updated"]

        # single record
        r = await client.get(f"/passport/{pid}/records/{rid}", headers=headers)
        assert r.status_code == 200
        assert r.json()["record"]["source"] == "ocr"


@pytest.mark.asyncio
async def test_passport_denies_other_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, _ = await _register_patient(client)
        other_headers, other_pid = await _register_patient(client)

        r = await client.get(f"/passport/{other_pid}", headers=headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_passport_404_unknown_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, _ = await _register_patient(client)
        r = await client.get(f"/passport/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_passport_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/passport/{uuid.uuid4()}")
        assert r.status_code == 401
