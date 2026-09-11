"""``POST /tumor-predict`` — 4-class MRI classification.

Returns all four class probabilities plus the argmax, and optionally a Grad-CAM
heatmap. ``with_heatmap`` is an additive field that defaults to false, so the
originally agreed body ``{image_b64}`` keeps working unchanged.

``503 model_unavailable`` when no trained checkpoint is present — the service
never invents a tumour class.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from schemas import TumorResponse
from services.tumor_service import SERVICE as tumor_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms
from utils.transport import TUMOR_FIELDS, TUMOR_FORM_FIELDS, read_payload

router = APIRouter(tags=["tumor"])


@router.post(
    "/tumor-predict",
    response_model=TumorResponse,
    summary="Classify an MRI slice into 4 tumour classes",
)
async def predict(request: Request) -> TumorResponse:
    # Accepts JSON {"image_b64": ..., "with_heatmap": bool} or a multipart upload
    # (field "dicom_file", "file" or "image"); see utils/transport.py.
    payload = await read_payload(
        request, json_fields=TUMOR_FIELDS, form_fields=TUMOR_FORM_FIELDS, label="image"
    )
    with_heatmap = payload.flag("with_heatmap")

    with InferenceTimer() as timer:
        result = tumor_service.predict(payload.value, with_heatmap=with_heatmap)

    record_inference(
        model_key=tumor_service.serving_key,
        endpoint="/tumor-predict",
        inference_time_ms=timer.elapsed_ms,
        input_size=result["input_size"],
        confidence=result["confidence"],
        degraded=False,
    )

    return TumorResponse(
        prediction=result["prediction"],
        confidence=result["confidence"],
        class_probabilities=result["class_probabilities"],
        heatmap_b64=result["heatmap_b64"],
        degraded=False,
        model_version=tumor_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
