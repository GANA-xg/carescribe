"""Face-ID routes. API contract: /faceid/*. OC-07.

POST   /faceid/enroll             — patient-only. Stores Fernet-encrypted
                                    embedding; raw image discarded.
POST   /faceid/identify           — doctor-only. FAISS search over all
                                    enrolled embeddings; returns best match
                                    + liveness verdict.
DELETE /faceid/unenroll/{pid}     — patient opt-out (own id) or doctor.
"""
import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user, require_doctor, require_patient
from database import get_db
from models.db import FaceEmbedding, Patient, User
from services import faceid
from services.faceid import search
from services.model_proxy import ModelServiceError, call_model

router = APIRouter(prefix="/faceid", tags=["faceid"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MATCH_THRESHOLD = 0.55  # cosine similarity; below this = no match
LIVENESS_THRESHOLD = 0.5


async def _validate_image(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image exceeds 10MB")
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(400, "File is not a valid image") from e
    return content


@router.post("/enroll")
async def enroll(
    file: UploadFile = File(...),
    patient: User = Depends(require_patient),
    db: AsyncSession = Depends(get_db),
):
    """Enroll the calling patient's face. Patient-only.

    The image is validated, sent to the model service for embedding
    extraction, and then DISCARDED — only the encrypted embedding row is
    stored. Enrolling again replaces the previous embedding.
    """
    content = await _validate_image(file)
    try:
        model_out = await call_model("/faceid/embed", content=content, filename=file.filename or "face.jpg")
    except ModelServiceError as e:
        raise HTTPException(502, f"Face model unavailable: {e}") from e

    embedding = model_out.get("embedding")
    if not embedding:
        raise HTTPException(422, "No face detected in image")

    profile = await db.scalar(select(Patient).where(Patient.user_id == patient.id))
    if profile is None:
        raise HTTPException(400, "Patient profile missing")

    # Replace any existing enrollment (one embedding per patient).
    await db.execute(delete(FaceEmbedding).where(FaceEmbedding.patient_id == profile.id))
    db.add(
        FaceEmbedding(
            patient_id=profile.id,
            embedding=faceid.encrypt_embedding(embedding),
            model_name=model_out.get("model_version", "arcface"),
        )
    )
    await db.commit()
    await faceid.rebuild_index()  # immediate convergence, no 5-min wait
    return {"enrolled": True}


@router.post("/identify")
async def identify(
    file: UploadFile = File(...),
    doctor: User = Depends(require_doctor),
):
    """Identify a patient by face. Doctor-only.

    Returns null patient fields when no enrolled face is close enough.
    Liveness comes from the model service's texture-heuristic verdict.
    """
    content = await _validate_image(file)
    try:
        model_out = await call_model("/faceid/embed", content=content, filename=file.filename or "face.jpg")
    except ModelServiceError as e:
        raise HTTPException(502, f"Face model unavailable: {e}") from e

    embedding = model_out.get("embedding")
    if not embedding:
        return {"patient_id": None, "name": None, "confidence": 0.0,
                "liveness_passed": False}

    if faceid.maybe_refresh():
        await faceid.rebuild_index()

    pid, name, score = search(embedding)
    matched = score >= MATCH_THRESHOLD
    return {
        "patient_id": str(pid) if matched else None,
        "name": name if matched else None,
        "confidence": round(score, 4),
        "liveness_passed": bool(model_out.get("liveness_passed", False)),
    }


@router.delete("/unenroll/{patient_id}")
async def unenroll(
    patient_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a face enrollment (patient opt-out). Any authenticated user;
    a patient can only unenroll their own face, a doctor can unenroll any.
    """
    if user.role == "patient":
        profile = await db.scalar(select(Patient).where(Patient.user_id == user.id))
        if profile is None or profile.id != patient_id:
            raise HTTPException(403, "Patients can only unenroll their own face")
    await db.execute(delete(FaceEmbedding).where(FaceEmbedding.patient_id == patient_id))
    await db.commit()
    await faceid.rebuild_index()
    return {"success": True}
