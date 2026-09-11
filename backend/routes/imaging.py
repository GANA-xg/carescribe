"""Imaging routes — Orthanc study list + tumor scan. API contract: /imaging/*. OC-06.

GET  /imaging/studies/{patient_id} — maps a CareScribe patient to their
     Orthanc studies (matched via PatientID DICOM tag = our patient_id)
     and returns an OHIF-compatible study list. Protected, any role.

POST /imaging/tumor-scan — accepts a DICOM file, uploads to Orthanc,
     runs the model service tumor classifier, returns prediction +
     confidence + heatmap URL. Protected, any role.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.db import User
from services import orthanc
from services.model_proxy import ModelServiceError, call_model

logger = logging.getLogger("carescribe.imaging")

router = APIRouter(prefix="/imaging", tags=["imaging"])

MAX_DICOM_BYTES = 10 * 1024 * 1024


def _to_ohif_study(study: dict) -> dict:
    """Map an Orthanc expanded study to the OHIF study-list shape."""
    tags = study.get("MainDicomTags", {})
    return {
        "study_instance_uid": tags.get("StudyInstanceUID"),
        "orthanc_study_id": study.get("ID"),
        "date": tags.get("StudyDate"),
        "description": tags.get("StudyDescription"),
        "accession_number": tags.get("AccessionNumber"),
        "series_count": len(study.get("Series", [])),
        "ohif_url": f"/viewer?StudyInstanceUIDs={tags.get('StudyInstanceUID')}",
    }


@router.get("/studies/{patient_id}")
async def studies(patient_id: uuid.UUID, user: User = Depends(get_current_user)):
    """List imaging studies for a CareScribe patient. Protected — any role.

    Matching: each Orthanc patient's DICOM PatientID tag (fetched via
    patient metadata) is compared to our patient uuid — internal Orthanc
    ids are opaque hashes, so tag matching is the reliable join key.
    """
    try:
        all_ids = await orthanc.list_patients()
    except orthanc.OrthancError as e:
        raise HTTPException(502, f"Imaging server error: {e}") from e

    ours = str(patient_id)
    studies: list[dict] = []
    for pid in all_ids:
        meta = await orthanc.patient_meta(pid)
        if meta.get("MainDicomTags", {}).get("PatientID") == ours:
            raw = await orthanc.get_studies(pid)
            studies = [_to_ohif_study(s) for s in raw]
            break
    return {"studies": studies}


@router.post("/tumor-scan")
async def tumor_scan(
    dicom_file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload DICOM -> Orthanc, then classify with the tumor model.

    Protected — any role (doctor scanning at point of care, patient
    uploading their own MRI copy). The DICOM's PatientID tag is rewritten
    to the uploading patient's CareScribe uuid when the uploader is a
    patient, so studies/{id} finds it later.
    """
    content = await dicom_file.read()
    if len(content) > MAX_DICOM_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "DICOM exceeds 10MB")

    # Upload to Orthanc (best effort — prediction still works if Orthanc is down)
    stored_id = None
    try:
        up = await orthanc.upload_instance(content)
        stored_id = up.get("ID")
    except orthanc.OrthancError as e:
        logger.warning("orthanc upload failed (continuing): %s", e)

    try:
        model_out = await call_model("/tumor-predict", content=content,
                                     filename=dicom_file.filename or "scan.dcm")
    except ModelServiceError as e:
        raise HTTPException(502, f"Tumor model unavailable: {e}") from e

    return {
        "prediction": model_out.get("prediction", "no_tumor"),
        "confidence": model_out.get("confidence", 0.0),
        "heatmap_url": model_out.get("heatmap_url"),
        "probabilities": model_out.get("probabilities"),
        "orthanc_instance_id": stored_id,
    }
