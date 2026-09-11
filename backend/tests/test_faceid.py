"""OC-07 tests — Face-ID enroll / identify / unenroll. Model mocked."""
import io
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from main import app
from routes import faceid as faceid_route
from services import faceid as faceid_svc

EMBEDDINGS = {}


def make_png(seed: int = 0) -> bytes:
    """Unique image per seed -> unique deterministic embedding per patient."""
    buf = io.BytesIO()
    img = Image.new("RGB", (64, 64), tuple((seed * 37 + c) % 256 for c in range(3)))
    img.save(buf, format="PNG")
    return buf.getvalue()


async def fake_call_model(path, *, json_body=None, content=None, filename=None, timeout=120):
    assert path == "/faceid/embed"
    # Deterministic per-pixel-sum embedding: similar images -> similar vectors.
    total = sum(content)
    base = [((total + i) % 17) / 17.0 for i in range(faceid_svc.DIM)]
    return {"embedding": base, "dim": faceid_svc.DIM,
            "liveness_score": 0.9, "liveness_passed": True,
            "model_version": "test"}


@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    monkeypatch.setattr(faceid_route, "call_model", fake_call_model)


async def _register(client: AsyncClient, role) -> dict:
    email = f"face-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": f"Face {role}", "email": email, "password": "testpass123", "role": role},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.asyncio
async def test_enroll_and_identify_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patient_headers = await _register(client, "patient")
        doctor_headers = await _register(client, "doctor")

        # patient enrolls
        r = await client.post("/faceid/enroll",
                              files={"file": ("face.png", make_png(101), "image/png")},
                              headers=patient_headers)
        assert r.status_code == 200, r.text
        assert r.json()["enrolled"] is True

        # doctor identifies with the same image -> same deterministic embedding
        r = await client.post("/faceid/identify",
                              files={"file": ("face.png", make_png(101), "image/png")},
                              headers=doctor_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["patient_id"] is not None, body
        assert body["name"] == "Face patient"
        assert body["confidence"] >= faceid_route.MATCH_THRESHOLD
        assert body["liveness_passed"] is True


@pytest.mark.asyncio
async def test_identify_requires_doctor():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patient_headers = await _register(client, "patient")
        r = await client.post("/faceid/identify",
                              files={"file": ("face.png", make_png(), "image/png")},
                              headers=patient_headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_enroll_requires_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        doctor_headers = await _register(client, "doctor")
        r = await client.post("/faceid/enroll",
                              files={"file": ("face.png", make_png(), "image/png")},
                              headers=doctor_headers)
        assert r.status_code == 403


@pytest.mark.asyncio
async def test_unenroll_purges_match():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        patient_headers = await _register(client, "patient")
        doctor_headers = await _register(client, "doctor")
        seed = uuid.uuid4().int % 10000

        # enroll
        await client.post("/faceid/enroll",
                          files={"file": ("face.png", make_png(seed), "image/png")},
                          headers=patient_headers)

        # find our patient id via identify
        r = await client.post("/faceid/identify",
                              files={"file": ("face.png", make_png(seed), "image/png")},
                              headers=doctor_headers)
        pid = r.json()["patient_id"]

        # unenroll own face
        r = await client.delete(f"/faceid/unenroll/{pid}", headers=patient_headers)
        assert r.status_code == 200 and r.json()["success"] is True

        # identify with THIS face now finds nothing (or a different face)
        r = await client.post("/faceid/identify",
                              files={"file": ("face.png", make_png(seed), "image/png")},
                              headers=doctor_headers)
        body = r.json()
        assert body["patient_id"] != pid


@pytest.mark.asyncio
async def test_patient_cannot_unenroll_other():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        h1 = await _register(client, "patient")
        await _register(client, "patient")  # second patient

        await client.post("/faceid/enroll",
                          files={"file": ("face.png", make_png(303), "image/png")},
                          headers=h1)
        other_pid = uuid.uuid4()
        r = await client.delete(f"/faceid/unenroll/{other_pid}", headers=h1)
        assert r.status_code == 403
