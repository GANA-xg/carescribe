"""Orthanc DICOM server client — REST API. OC-06."""
import os

import httpx

ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042")


class OrthancError(Exception):
    """Orthanc REST call failed."""


async def _request(method: str, path: str, *, content: bytes | None = None,
                   params: dict | None = None) -> httpx.Response:
    """One Orthanc call. Dev Orthanc runs with auth disabled (see infra config)."""
    async with httpx.AsyncClient(timeout=60) as client:
        return await client.request(method, f"{ORTHANC_URL}{path}", content=content, params=params)


async def list_patients() -> list[str]:
    """All Orthanc patient ids."""
    resp = await _request("GET", "/patients")
    if resp.status_code != 200:
        raise OrthancError(f"list patients: {resp.status_code}")
    return resp.json()


async def get_studies(patient_orthanc_id: str) -> list[dict]:
    """Expanded studies for one Orthanc patient id."""
    resp = await _request("GET", f"/patients/{patient_orthanc_id}/studies?expanded")
    if resp.status_code == 404:
        return []
    if resp.status_code != 200:
        raise OrthancError(f"studies: {resp.status_code}")
    return resp.json()


async def upload_instance(dicom_bytes: bytes) -> dict:
    """Upload one DICOM instance. Returns {id, parent_patient, ...}."""
    resp = await _request("POST", "/instances", content=dicom_bytes,
                          params={"ignore-errors": "all"})
    if resp.status_code != 200:
        raise OrthancError(f"upload: {resp.status_code} {resp.text[:200]}")
    return resp.json()


async def patient_meta(patient_orthanc_id: str) -> dict:
    """Main DICOM tags for a patient."""
    resp = await _request("GET", f"/patients/{patient_orthanc_id}")
    if resp.status_code != 200:
        raise OrthancError(f"patient meta: {resp.status_code}")
    return resp.json()
