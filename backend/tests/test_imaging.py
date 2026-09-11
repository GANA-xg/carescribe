"""OC-06 tests — imaging routes. Orthanc is real (dev stack), model mocked."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from main import app
from routes import imaging as imaging_route
from services import dicom_seed


FAKE_TUMOR = {
    "prediction": "glioma",
    "confidence": 0.87,
    "heatmap_url": None,
    "probabilities": {"glioma": 0.87, "meningioma": 0.05, "no_tumor": 0.03, "pituitary": 0.05},
}


async def fake_call_model(path, *, json_body=None, content=None, filename=None, timeout=120):
    assert path == "/tumor-predict"
    return FAKE_TUMOR


@pytest.fixture(autouse=True)
def patch_model(monkeypatch):
    monkeypatch.setattr(imaging_route, "call_model", fake_call_model)


async def _login(client: AsyncClient, role="doctor"):
    email = f"img-{uuid.uuid4().hex[:8]}@example.com"
    r = await client.post(
        "/auth/register",
        json={"name": "Imaging User", "email": email, "password": "testpass123", "role": role},
    )
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.mark.asyncio
async def test_tumor_scan_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _login(client)
        dicom = dicom_seed.build_sample_dicom()
        r = await client.post(
            "/imaging/tumor-scan",
            files={"dicom_file": ("mri.dcm", dicom, "application/dicom")},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["prediction"] == "glioma"
        assert abs(body["confidence"] - 0.87) < 1e-6
        assert body["orthanc_instance_id"]  # stored in Orthanc


@pytest.mark.asyncio
async def test_studies_for_seed_patient():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _login(client)
        # The startup seeder stores the sample under PatientID seed-mri-patient.
        r = await client.get(f"/imaging/studies/{dicom_seed.SAMPLE_PATIENT_ID}", headers=headers)
        assert r.status_code == 200
        studies = r.json()["studies"]
        assert len(studies) >= 1
        assert studies[0]["study_instance_uid"]
        assert "viewer?StudyInstanceUIDs=" in studies[0]["ohif_url"]


@pytest.mark.asyncio
async def test_studies_unknown_patient_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = await _login(client)
        r = await client.get(f"/imaging/studies/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 200
        assert r.json()["studies"] == []


@pytest.mark.asyncio
async def test_imaging_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get(f"/imaging/studies/{uuid.uuid4()}")
        assert r.status_code == 401
