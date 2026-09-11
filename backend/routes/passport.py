"""Health Passport routes. API contract: /passport/*. OC-08.

GET  /passport/{patient_id}               — unified view: HealthRecord rows
         + OpenEMR FHIR records (when the patient is linked), plus a
         summary {total, last_updated, conditions[], medications[]}.
GET  /passport/{patient_id}/records/{rid} — single record.
POST /passport/{patient_id}/records       — write a record (ocr|manual).

Access: patients can read/write only their own passport; doctors can
access any patient's passport. Writes via OCR flow use source="ocr".
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Literal

from auth import get_current_user
from database import get_db
from models.db import HealthRecord, Patient, User
from services import openemr
from services.openemr import OpenEMRError

router = APIRouter(prefix="/passport", tags=["passport"])


async def _authorize(patient_id: uuid.UUID, user: User, db: AsyncSession) -> Patient:
    """Load the patient or 404; enforce patient-scoped access."""
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
    if user.role == "patient":
        if patient.user_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your passport")
    return patient


def _record_out(rec: HealthRecord) -> dict:
    return {
        "id": str(rec.id),
        "type": rec.type,
        "data": rec.data,
        "source": rec.source,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


@router.get("/{patient_id}")
async def get_passport(patient_id: uuid.UUID, user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """Unified health passport. Protected — patient (own) or doctor."""
    patient = await _authorize(patient_id, user, db)

    records = (
        await db.execute(
            select(HealthRecord)
            .where(HealthRecord.patient_id == patient_id)
            .order_by(HealthRecord.created_at.desc())
        )
    ).scalars().all()

    # Merge in OpenEMR FHIR resources when the patient is linked.
    fhir_resources: list[dict] = []
    if patient.openemr_patient_id:
        try:
            fhir_resources = await openemr.get_patient_records(patient.openemr_patient_id)
        except OpenEMRError:
            fhir_resources = []  # OpenEMR down must not break the passport

    conditions: list[str] = []
    medications: list[str] = []
    for rec in records:
        data = rec.data or {}
        if rec.type == "diagnosis" and data.get("diagnosis"):
            conditions.append(data["diagnosis"])
        if rec.type == "prescription":
            for drug in data.get("drugs", []):
                name = drug.get("name") if isinstance(drug, dict) else None
                if name:
                    medications.append(name)
    for res in fhir_resources:
        if res.get("resourceType") == "Condition":
            code = res.get("code", {}).get("text") or res.get("code", {}).get("coding", [{}])[0].get("display")
            if code:
                conditions.append(code)
        if res.get("resourceType") == "MedicationRequest":
            med = res.get("medicationCodeableConcept", {}).get("text")
            if med:
                medications.append(med)

    all_records = [_record_out(r) for r in records]
    last_updated = records[0].created_at.isoformat() if records else None

    return {
        "records": all_records,
        "fhir_resources": fhir_resources,
        "summary": {
            "total": len(all_records),
            "last_updated": last_updated,
            "conditions": sorted(set(conditions)),
            "medications": sorted(set(medications)),
        },
    }


class RecordIn(BaseModel):
    type: str = Field(max_length=64)
    data: dict
    source: Literal["ocr", "manual"] = "manual"


@router.post("/{patient_id}/records", status_code=status.HTTP_201_CREATED)
async def add_record(patient_id: uuid.UUID, body: RecordIn,
                     user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Write a health record. Protected — patient (own) or doctor."""
    await _authorize(patient_id, user, db)
    rec = HealthRecord(patient_id=patient_id, type=body.type, data=body.data, source=body.source)
    db.add(rec)
    await db.commit()
    await db.refresh(rec)
    return {"record": _record_out(rec)}


@router.get("/{patient_id}/records/{record_id}")
async def get_record(patient_id: uuid.UUID, record_id: uuid.UUID,
                     user: User = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Fetch a single record. Protected — patient (own) or doctor."""
    await _authorize(patient_id, user, db)
    rec = await db.get(HealthRecord, record_id)
    if rec is None or rec.patient_id != patient_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Record not found")
    return {"record": _record_out(rec)}
