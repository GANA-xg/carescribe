"""OpenEMR FHIR R4 client — server-side only. OC-04.

Wraps the OpenEMR FHIR API with an async httpx client:
    get_patient(openemr_id)      -> FHIR Patient resource
    list_patients()              -> list of Patient summaries
    create_patient(data)         -> creates Patient, returns openemr_id
    get_patient_records(openemr_id) -> FHIR Bundle of records

Auth: OAuth2 client-credentials against OPENEMR_TOKEN_URL. Token cached
in memory with a TTL (refreshed 60s before expiry). Credentials come
from OPENEMR_CLIENT_ID / OPENEMR_CLIENT_SECRET env vars — NEVER exposed
to the frontend (security rule 4).
"""
import os
import time
import logging
import uuid

import httpx

logger = logging.getLogger("carescribe.openemr")

BASE_URL = os.getenv("OPENEMR_BASE_URL", "http://openemr:80/apis/default/fhir")
TOKEN_URL = os.getenv("OPENEMR_TOKEN_URL", "http://openemr:80/apis/default/token")
CLIENT_ID = os.getenv("OPENEMR_CLIENT_ID", "carescribe-backend")
CLIENT_SECRET = os.getenv("OPENEMR_CLIENT_SECRET", "")

# In-memory token cache: (token, expires_at)
_token_cache: tuple[str, float] | None = None
_TTL_MARGIN = 60  # refresh 60s before actual expiry


class OpenEMRError(Exception):
    """Raised when OpenEMR FHIR returns an unexpected failure."""


def reset_token_cache() -> None:
    """Test hook — clear the cached token."""
    global _token_cache
    _token_cache = None


async def _get_token(client: httpx.AsyncClient) -> str:
    """Return a valid access token, refreshing the cache if needed."""
    global _token_cache
    if _token_cache and _token_cache[1] > time.time() + _TTL_MARGIN:
        return _token_cache[0]

    resp = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    )
    if resp.status_code != 200:
        raise OpenEMRError(f"token request failed: {resp.status_code} {resp.text[:200]}")
    payload = resp.json()
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache = (payload["access_token"], time.time() + expires_in)
    return _token_cache[0]


async def _fhir_request(
    method: str,
    path: str,
    json_body: dict | None = None,
    params: dict | None = None,
) -> httpx.Response:
    """One authenticated FHIR call. Opens a fresh client per call —
    acceptable for MVP; a shared AsyncClient is an OC-15 optimization."""
    async with httpx.AsyncClient(timeout=30) as client:
        token = await _get_token(client)
        return await client.request(
            method,
            f"{BASE_URL}{path}",
            json=json_body,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )


async def get_patient(openemr_id: str) -> dict:
    """Fetch a single FHIR Patient resource by OpenEMR id."""
    resp = await _fhir_request("GET", f"/Patient/{openemr_id}")
    if resp.status_code == 404:
        raise OpenEMRError(f"patient {openemr_id} not found")
    if resp.status_code != 200:
        raise OpenEMRError(f"get_patient failed: {resp.status_code}")
    return resp.json()


async def list_patients() -> list[dict]:
    """List Patient summaries (id, name) for all patients in OpenEMR."""
    resp = await _fhir_request("GET", "/Patient", params={"_count": 100})
    if resp.status_code != 200:
        raise OpenEMRError(f"list_patients failed: {resp.status_code}")
    bundle = resp.json()
    summaries = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        names = res.get("name", [{}])
        summaries.append(
            {
                "openemr_id": res.get("id"),
                "name": " ".join(
                    (names[0].get("given") or []) + [names[0].get("family") or ""]
                ).strip(),
                "gender": res.get("gender"),
                "birth_date": res.get("birthDate"),
            }
        )
    return summaries


async def create_patient(data: dict) -> str:
    """Create a FHIR Patient; returns the new openemr_id."""
    body = {
        "resourceType": "Patient",
        "name": [{"given": [data.get("name", "Unknown")], "family": data.get("family", "")}],
    }
    if data.get("gender"):
        body["gender"] = data["gender"]
    if data.get("dob"):
        body["birthDate"] = str(data["dob"])

    resp = await _fhir_request("POST", "/Patient", json_body=body)
    if resp.status_code not in (200, 201):
        raise OpenEMRError(f"create_patient failed: {resp.status_code} {resp.text[:200]}")
    created = resp.json()
    return created.get("id") or str(uuid.uuid4())


async def get_patient_records(openemr_id: str) -> list[dict]:
    """Fetch the patient's record Bundle ($everything). Falls back to a
    /Condition search when the OpenEMR build does not support $everything."""
    resp = await _fhir_request("GET", f"/Patient/{openemr_id}/$everything")
    if resp.status_code == 404:
        # Fallback: plain search for resources referencing this patient.
        resp = await _fhir_request("GET", "/Condition", params={"patient": openemr_id})
    if resp.status_code != 200:
        raise OpenEMRError(f"get_patient_records failed: {resp.status_code}")
    bundle = resp.json()
    return [e.get("resource", {}) for e in bundle.get("entry", [])]
