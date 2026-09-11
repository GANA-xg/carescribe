"""``POST /ner`` — structured extraction from raw prescription text.

The backend calls this after OCR when it needs fields rather than a transcript,
and reuses it to sanity-check the OCR service's own merge step.
"""

from __future__ import annotations

from fastapi import APIRouter

from schemas import NerResponse, TextRequest
from services.ner_service import SERVICE as ner_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms

router = APIRouter(tags=["ner"])


@router.post("/ner", response_model=NerResponse, summary="Clinical NER over text")
def extract_entities(request: TextRequest) -> NerResponse:
    with InferenceTimer() as timer:
        result = ner_service.extract(request.text)

    confidence = float(result["confidence"])
    record_inference(
        model_key=ner_service.serving_key,
        endpoint="/ner",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{len(request.text)} chars",
        confidence=confidence,
        degraded=bool(result["degraded"]),
    )

    return NerResponse(
        drugs=list(result["drugs"]),
        dosages=list(result["dosages"]),
        frequencies=list(result["frequencies"]),
        diagnosis=str(result["diagnosis"]),
        engine=str(result["engine"]),
        degraded=bool(result["degraded"]),
        confidence=confidence,
        model_version=ner_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
