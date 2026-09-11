"""OC-12 + OC-13 tests — RAG assistant chat/voice + diagnosis compare."""
import io
import uuid
import wave

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from main import app
from routes import assistant as assistant_route
from database import SessionLocal
from models.db import Patient, User


def make_wav(seconds: float = 0.5) -> bytes:
    """A tiny valid WAV file."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


async def _register_with_records(client: AsyncClient):
    """Register a patient and add two health records for RAG."""
    email = f"rag-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": "Rag Patient", "email": email, "password": "testpass123", "role": "patient"},
    )
    token = r.json()["token"]
    async with SessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == email))
        pid = (await session.scalar(select(Patient).where(Patient.user_id == u.id))).id

    headers = {"Authorization": f"Bearer {token}"}
    for rec in [
        {"type": "prescription", "data": {"drugs": [{"name": "Metformin", "dosage": "500mg"}], "text": "Metformin 500mg twice daily for type 2 diabetes"}, "source": "ocr"},
        {"type": "diagnosis", "data": {"diagnosis": "Type 2 diabetes mellitus"}, "source": "manual"},
    ]:
        await client.post(f"/passport/{pid}/records", headers=headers, json=rec)
    return headers, pid


@pytest.mark.asyncio
async def test_chat_cites_records():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, pid = await _register_with_records(client)

        r = await client.post("/assistant/chat", headers=headers, json={
            "patient_id": str(pid),
            "message": "What diabetes medication am I on?",
            "history": [],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert "Metformin" in body["reply"]  # grounded in the record
        assert body["sources"]  # citations present


@pytest.mark.asyncio
async def test_chat_denies_other_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, _ = await _register_with_records(client)
        other_headers, other_pid = await _register_with_records(client)

        r = await client.post("/assistant/chat", headers=headers, json={
            "patient_id": str(other_pid),
            "message": "hello",
            "history": [],
        })
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_voice_flow(monkeypatch):
    """STT + TTS mocked; RAG path real."""
    async def fake_call_model(path, *, json_body=None, content=None, filename=None, timeout=120):
        if path == "/stt":
            return {"transcript": "What medication do I take?", "language_detected": "en"}
        if path == "/tts":
            return {"audio_b64": "AAAA", "audio_format": "wav", "duration_s": 2.0}
        raise AssertionError(f"unexpected {path}")

    monkeypatch.setattr(assistant_route, "call_model", fake_call_model)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers, pid = await _register_with_records(client)

        r = await client.post(
            "/assistant/voice",
            params={"patient_id": str(pid)},
            files={"audio_file": ("q.wav", make_wav(), "audio/wav")},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["transcript"] == "What medication do I take?"
        assert "Metformin" in body["reply"]
        assert body["audio_reply_url"].startswith("data:audio/wav;base64,")
        assert body["sources"]


@pytest.mark.asyncio
async def test_diagnosis_exact_agreement():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/diagnosis/compare", json={
            "diagnosis_a": "Type 2 diabetes mellitus",
            "diagnosis_b": "E11",
            "date_a": "2026-01-01",
            "date_b": "2026-02-01",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["agreement"] is True
        assert body["icd_codes"] == ["E11", "E11"]


@pytest.mark.asyncio
async def test_diagnosis_conflict_detected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/diagnosis/compare", json={
            "diagnosis_a": "Type 2 diabetes mellitus",
            "diagnosis_b": "Acute appendicitis with peritonitis",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["agreement"] is False
        assert body["conflict_details"]
