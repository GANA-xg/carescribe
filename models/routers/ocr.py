"""``POST /ocr`` — dual-engine prescription OCR.

Returns Donut's output, Chandra's output, and the merged result separately, so
the backend decides which to trust (rule 4).

Each engine is logged with its own latency, and the merge with the cross-engine
agreement as its confidence. That is what makes the paper's OCR comparison table
possible straight out of the running service.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from schemas import (
    ChandraOutput,
    DonutOutput,
    MergedOutput,
    OcrResponse,
    StructuredPrescription,
)
from services.ocr_service import SERVICE as ocr_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms
from utils.transport import IMAGE_BODY, OCR_FIELDS, OCR_FORM_FIELDS, read_payload

router = APIRouter(tags=["ocr"])


def _record_engines(result: dict[str, Any]) -> None:
    """Log one row per available engine plus one for the merge."""
    timings: dict[str, float] = result.get("timings", {})
    input_size = result.get("input_size")

    for engine in ("donut", "chandra"):
        payload = result[engine]
        if not payload["text"] and not payload["confidence"]:
            continue  # engine was unavailable; do not pollute the log
        record_inference(
            model_key=engine,
            endpoint="/ocr",
            inference_time_ms=timings.get(engine, 0.0),
            input_size=input_size,
            confidence=payload["confidence"],
            degraded=False,
        )

    record_inference(
        model_key="ocr_merge",
        endpoint="/ocr",
        inference_time_ms=timings.get("merge", 0.0),
        input_size=input_size,
        confidence=result["agreement"],
        degraded=bool(result["degraded"]),
    )


@router.post(
    "/ocr",
    response_model=OcrResponse,
    openapi_extra=IMAGE_BODY,
    summary="Dual-engine prescription OCR",
)
async def process_document(request: Request) -> OcrResponse:
    # Accepts JSON {"image_b64": ...} or a multipart file upload; see utils/transport.py.
    payload = await read_payload(
        request, json_fields=OCR_FIELDS, form_fields=OCR_FORM_FIELDS, label="image"
    )

    with InferenceTimer() as timer:
        result = ocr_service.process(payload.value)

    _record_engines(result)
    merged = result["merged"]

    return OcrResponse(
        donut=DonutOutput(**result["donut"]),
        chandra=ChandraOutput(**result["chandra"]),
        merged=MergedOutput(
            structured=StructuredPrescription(**merged["structured"]),
            text=merged["text"],
            engine=merged["engine"],
            drug_agreement=merged["drug_agreement"],
        ),
        agreement=result["agreement"],
        engines=result["engines"],
        timings={key: round_ms(value) for key, value in result["timings"].items()},
        degraded=bool(result["degraded"]),
        model_version=ocr_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
