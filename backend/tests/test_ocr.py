"""OC-05 tests — OCR async job flow.

The model service call is mocked (it's FreeBuff's service); Redis is real
(running in the dev stack). Image is a tiny generated PNG.
"""
import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from main import app
from routes import ocr as ocr_route
from services import job_store


def make_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    return buf.getvalue()


FAKE_MODEL_RESPONSE = {
    "merged": {
        "text": "Rx Amoxicillin 500mg 1-0-1 x5d",
        "structured": {"drugs": [{"name": "Amoxicillin", "dosage": "500mg"}], "diagnosis": "URTI", "date": "2026-09-11"},
        "engine": "chandra",
        "drug_agreement": 1.0,
    },
    "agreement": 0.92,
    "engines": {"donut": "stub", "chandra": "stub"},
}


async def fake_call_model(path, *, json_body=None, content=None, filename=None, timeout=120):
    assert path == "/ocr"
    return FAKE_MODEL_RESPONSE


@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    monkeypatch.setattr(ocr_route, "call_model", fake_call_model)


async def _login(client: AsyncClient) -> dict:
    email = f"ocruser-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": "OCR User", "email": email, "password": "testpass123", "role": "patient"},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.asyncio
async def test_ocr_full_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _login(client)

        r = await client.post(
            "/ocr/process",
            files={"file": ("rx.png", make_png(), "image/png")},
            headers=headers,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "queued" and body["job_id"]

        # background tasks run after the response in TestClient... with raw
        # ASGITransport they need a tick; poll until done.
        for _ in range(20):
            s = await client.get(f"/ocr/status/{body['job_id']}")
            if s.json()["status"] == "done":
                break
            await job_store.set_job(body["job_id"], {"status": "queued"}) if False else None
            import asyncio
            await asyncio.sleep(0.05)
            # re-run background task if pending (ASGITransport runs BG tasks
            # after response completes — normally already done by now)
        assert s.status_code == 200
        result = s.json()["result"]
        assert result["raw_text"].startswith("Rx Amoxicillin")
        assert result["structured"]["drugs"][0]["name"] == "Amoxicillin"
        assert result["model_used"] == "chandra"
        assert abs(result["confidence"] - 0.92) < 1e-6


@pytest.mark.asyncio
async def test_ocr_rejects_non_image():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _login(client)
        r = await client.post(
            "/ocr/process",
            files={"file": ("note.txt", b"not an image", "text/plain")},
            headers=headers,
        )
        assert r.status_code == 400


@pytest.mark.asyncio
async def test_ocr_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/ocr/process",
            files={"file": ("rx.png", make_png(), "image/png")},
        )
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_ocr_unknown_job_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/ocr/status/nonexistent")
        assert r.status_code == 404
