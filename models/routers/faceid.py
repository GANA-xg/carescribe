"""``POST /faceid/embed`` — one ArcFace embedding for one face.

Error contract (from the brief):

* ``422 no_face_detected`` — zero faces, or more than one;
* ``503 model_unavailable`` — the recognition backend is not installed.
   Deliberately **not** a fabricated embedding; see ``services/faceid_service``.

Enrolment (storing the vector, and later FAISS lookup) belongs to the backend.
This service only extracts.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from schemas import FaceEmbedResponse
from services.faceid_service import SERVICE as faceid_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms
from utils.transport import FACEID_FIELDS, FACEID_FORM_FIELDS, IMAGE_BODY, read_payload

router = APIRouter(tags=["faceid"])


@router.post(
    "/faceid/embed",
    response_model=FaceEmbedResponse,
    openapi_extra=IMAGE_BODY,
    summary="Extract an ArcFace embedding and liveness score",
)
async def embed_face(request: Request) -> FaceEmbedResponse:
    # Accepts JSON {"image_b64": ...} or a multipart upload (field "image" or "file").
    payload = await read_payload(
        request, json_fields=FACEID_FIELDS, form_fields=FACEID_FORM_FIELDS, label="image"
    )

    with InferenceTimer() as timer:
        result = faceid_service.embed(payload.value)

    record_inference(
        model_key=faceid_service.serving_key,
        endpoint="/faceid/embed",
        inference_time_ms=timer.elapsed_ms,
        input_size=result["input_size"],
        confidence=result["liveness_score"],
        degraded=False,
    )

    return FaceEmbedResponse(
        embedding=result["embedding"],
        dim=result["dim"],
        liveness_score=result["liveness_score"],
        liveness_passed=result["liveness_passed"],
        liveness_method=result["liveness_method"],
        model_version=faceid_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
