"""OC-10 + OC-11 tests — symptom checker + sepsis risk. Model mocked."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from routes import clinical as clinical_route
from routes import symptoms as symptoms_route


class FakeModel:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def __call__(self, path, *, json_body=None, content=None, filename=None, timeout=120):
        self.calls.append((path, json_body))
        return self.response


@pytest.mark.asyncio
async def test_symptom_check_maps_response(monkeypatch):
    fake = FakeModel({
        "conditions": [{"name": "Influenza", "score": 0.8}, {"name": "Common cold", "score": 0.6}],
        "severity": "medium",
        "see_doctor": False,
    })
    monkeypatch.setattr(symptoms_route, "call_model", fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/symptoms/check", json={"symptoms": ["fever", "cough", "body ache"]})
        assert r.status_code == 200
        body = r.json()
        assert body["possible_conditions"][0]["name"] == "Influenza"
        assert body["severity"] == "medium"
        assert body["see_doctor"] is False
        assert fake.calls[0][0] == "/symptoms"


@pytest.mark.asyncio
async def test_symptom_high_severity_forces_see_doctor(monkeypatch):
    """Contract rule: severity high -> see_doctor ALWAYS true."""
    fake = FakeModel({"conditions": [{"name": "Sepsis", "score": 0.9}],
                      "severity": "high", "see_doctor": False})
    monkeypatch.setattr(symptoms_route, "call_model", fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/symptoms/check", json={"symptoms": ["fever", "confusion", "rapid heartbeat"]})
        assert r.status_code == 200
        assert r.json()["see_doctor"] is True


@pytest.mark.asyncio
async def test_sepsis_risk_doctor_only():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        email = f"pat-{uuid.uuid4().hex[:6]}@example.com"
        r = await client.post("/auth/register",
                              json={"name": "S", "email": email, "password": "testpass123", "role": "patient"})
        token = r.json()["token"]
        r = await client.post("/clinical/sepsis-risk",
                              headers={"Authorization": f"Bearer {token}"},
                              json={"patient_id": str(uuid.uuid4()),
                                    "vitals": {"temp": 38.5, "hr": 110, "rr": 22, "wbc": 14, "lactate": 2.5}})
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_sepsis_risk_full_flow(monkeypatch):
    fake = FakeModel({
        "risk_score": 72.0, "risk_level": "high",
        "shap_values": [{"feature": "lactate", "value": 0.4}, {"feature": "temp", "value": 0.3}],
        "explanation": "lactate and temp drive risk",
    })
    monkeypatch.setattr(clinical_route, "call_model", fake)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register patient + doctor
        pat = await client.post("/auth/register", json={
            "name": "Sepsis Pat", "email": f"sepspat-{uuid.uuid4().hex[:6]}@example.com",
            "password": "testpass123", "role": "patient"})
        doc = await client.post("/auth/register", json={
            "name": "Sepsis Doc", "email": f"sepsdoc-{uuid.uuid4().hex[:6]}@example.com",
            "password": "testpass123", "role": "doctor"})

        # patient_id from passport
        from database import SessionLocal
        from models.db import User, Patient
        from sqlalchemy import select
        async with SessionLocal() as session:
            u = await session.scalar(select(User).where(User.email == pat.json()["user"]["email"]))
            pid = (await session.scalar(select(Patient).where(Patient.user_id == u.id))).id

        r = await client.post("/clinical/sepsis-risk",
                              headers={"Authorization": f"Bearer {doc.json()['token']}"},
                              json={"patient_id": str(pid),
                                    "vitals": {"temp": 38.9, "hr": 118, "rr": 26, "wbc": 16.2, "lactate": 3.1}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["risk_score"] == 72.0
        assert body["risk_level"] == "high"
        assert body["shap_explanation"][0]["feature"] == "lactate"
        assert body["record_id"]  # persisted to HealthRecord


@pytest.mark.asyncio
async def test_sepsis_risk_rejects_bad_vitals(monkeypatch):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        doc = await client.post("/auth/register", json={
            "name": "D2", "email": f"d2-{uuid.uuid4().hex[:6]}@example.com",
            "password": "testpass123", "role": "doctor"})
        r = await client.post("/clinical/sepsis-risk",
                              headers={"Authorization": f"Bearer {doc.json()['token']}"},
                              json={"patient_id": str(uuid.uuid4()),
                                    "vitals": {"temp": 99, "hr": 110, "rr": 22, "wbc": 14, "lactate": 2.5}})
        assert r.status_code == 422  # temp out of range
