"""OCR routes — async job pattern. API contract: /ocr/*. OC-05.

POST /ocr/process        -> validate image (Pillow), enqueue background task,
                            return {job_id, status: "queued"}. Protected.
GET  /ocr/status/{job_id} -> {status, result?} where status is one of
                            queued | processing | done | failed.
                            Public to the uploading user via job_id
                            (job ids are unguessable UUIDs).

The background task calls the model service (models:9000/ocr) and maps
FreeBuff's dual-engine response into the API contract shape:
    raw_text   <- merged.text
    structured <- merged.structured {drugs[], diagnosis, date}
    model_used <- merged.engine (+ "donut+chandra" agreement info)
    confidence <- agreement
"""
import io
import uuid
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.db import User
from schemas import OcrStatusResponse
from services import job_store
from services.model_proxy import ModelServiceError, call_model

logger = logging.getLogger("carescribe.ocr")

router = APIRouter(prefix="/ocr", tags=["ocr"])

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # OC-14 aligns: 10MB upload cap


@router.post("/process", response_model=dict, status_code=status.HTTP_202_ACCEPTED)
async def process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a prescription image for OCR. Returns a job_id immediately.

    Protected — any authenticated user (patient uploading their Rx,
    doctor scanning at point of care).
    """
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image exceeds 10MB")
    try:
        img = Image.open(io.BytesIO(content))
        img.verify()  # raises if not a real image
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is not a valid image") from e

    job_id = uuid.uuid4().hex
    await job_store.set_job(job_id, {"status": "queued"})
    background_tasks.add_task(_run_ocr, job_id, content, file.filename or "upload.jpg")
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}", response_model=OcrStatusResponse)
async def ocr_status(job_id: str):
    """Poll an OCR job. Public — job_id is an unguessable UUID capability."""
    job = await job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown or expired job")
    return OcrStatusResponse(status=job["status"], result=job.get("result"))


async def _run_ocr(job_id: str, content: bytes, filename: str) -> None:
    """Background worker: call model service, map to contract shape, store."""
    await job_store.set_job(job_id, {"status": "processing"})
    try:
        raw = await call_model("/ocr", content=content, filename=filename)

        merged = raw.get("merged", {})
        result = {
            "raw_text": merged.get("text", ""),
            "structured": merged.get("structured", {}),
            "model_used": merged.get("engine", "unknown"),
            "confidence": raw.get("agreement", 0.0),
            "engines": raw.get("engines", {}),
        }
        await job_store.set_job(job_id, {"status": "done", "result": result})
    except ModelServiceError as e:
        logger.warning("ocr job %s failed: %s", job_id, e)
        await job_store.set_job(job_id, {"status": "failed", "error": str(e)})
    except Exception:
        logger.exception("ocr job %s crashed", job_id)
        await job_store.set_job(job_id, {"status": "failed", "error": "internal error"})
