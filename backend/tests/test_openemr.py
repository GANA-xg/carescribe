"""OC-04 tests — OpenEMR FHIR client, fully mocked (no live OpenEMR needed).

Mock strategy: monkeypatch services.openemr._fhir_request and _get_token
so no real HTTP happens; verify call shapes + response mapping.
"""
import pytest

import services.openemr as oemr


class MockResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def clear_token_cache():
    oemr.reset_token_cache()
    yield
    oemr.reset_token_cache()


@pytest.mark.asyncio
async def test_get_token_caches(monkeypatch):
    calls = {"n": 0}

    async def fake_post(self, url, data=None, **kw):
        calls["n"] += 1
        return MockResponse(200, {"access_token": f"tok{calls['n']}", "expires_in": 3600})

    monkeypatch.setattr(oemr.httpx.AsyncClient, "post", fake_post)

    async with oemr.httpx.AsyncClient() as client:
        t1 = await oemr._get_token(client)
        t2 = await oemr._get_token(client)
    assert t1 == t2 == "tok1"  # second call served from cache
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_get_patient_success(monkeypatch):
    async def fake_req(method, path, json_body=None, params=None):
        assert method == "GET" and path == "/Patient/17"
        return MockResponse(200, {"resourceType": "Patient", "id": "17"})

    monkeypatch.setattr(oemr, "_fhir_request", fake_req)
    patient = await oemr.get_patient("17")
    assert patient["id"] == "17"


@pytest.mark.asyncio
async def test_get_patient_404(monkeypatch):
    async def fake_req(method, path, json_body=None, params=None):
        return MockResponse(404, {})
    monkeypatch.setattr(oemr, "_fhir_request", fake_req)
    with pytest.raises(oemr.OpenEMRError, match="not found"):
        await oemr.get_patient("999")


@pytest.mark.asyncio
async def test_list_patients_maps_names(monkeypatch):
    bundle = {
        "entry": [
            {"resource": {"id": "1", "name": [{"given": ["Rani"], "family": "Devi"}], "gender": "female"}},
            {"resource": {"id": "2", "name": [{"given": ["Arun"], "family": "Kumar"}]}},
        ]
    }

    async def fake_req(method, path, json_body=None, params=None):
        assert path == "/Patient"
        return MockResponse(200, bundle)

    monkeypatch.setattr(oemr, "_fhir_request", fake_req)
    patients = await oemr.list_patients()
    assert len(patients) == 2
    assert patients[0]["name"] == "Rani Devi"
    assert patients[0]["openemr_id"] == "1"
    assert patients[1]["gender"] is None


@pytest.mark.asyncio
async def test_create_patient_returns_id(monkeypatch):
    async def fake_req(method, path, json_body=None, params=None):
        assert method == "POST" and path == "/Patient"
        assert json_body["resourceType"] == "Patient"
        return MockResponse(201, {"id": "new-42"})

    monkeypatch.setattr(oemr, "_fhir_request", fake_req)
    new_id = await oemr.create_patient({"name": "Sita", "gender": "female", "dob": "1990-01-01"})
    assert new_id == "new-42"


@pytest.mark.asyncio
async def test_get_patient_records_fallback(monkeypatch):
    """$everything 404s -> falls back to /Condition search."""
    calls = []

    async def fake_req(method, path, json_body=None, params=None):
        calls.append(path)
        if path == "/Patient/7/$everything":
            return MockResponse(404, {})
        return MockResponse(200, {"entry": [{"resource": {"resourceType": "Condition", "id": "c1"}}]})

    monkeypatch.setattr(oemr, "_fhir_request", fake_req)
    records = await oemr.get_patient_records("7")
    assert records[0]["id"] == "c1"
    assert "/Condition" in calls
