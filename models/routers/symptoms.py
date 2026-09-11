"""``POST /symptoms`` — symptom triage.

Returns ranked candidate conditions, a severity band and whether the patient
should see a doctor. The backend's public contract exposes
``possible_conditions[]``, ``severity`` and ``see_doctor``; ``condition_scores``
is additive detail so the UI can rank without a second call.
"""

from __future__ import annotations

from fastapi import APIRouter

from schemas import ConditionScore, SymptomsRequest, SymptomsResponse
from services.symptoms_service import DISCLAIMER
from services.symptoms_service import SERVICE as symptoms_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms

router = APIRouter(tags=["symptoms"])


@router.post(
    "/symptoms",
    response_model=SymptomsResponse,
    summary="Rank conditions for a symptom list and assign triage severity",
)
def check_symptoms(request: SymptomsRequest) -> SymptomsResponse:
    with InferenceTimer() as timer:
        result = symptoms_service.check(request.symptoms)

    record_inference(
        model_key=symptoms_service.serving_key,
        endpoint="/symptoms",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{len(request.symptoms)} symptoms",
        confidence=float(result["confidence"]),
        degraded=bool(result["degraded"]),
    )

    return SymptomsResponse(
        conditions=result["conditions"],
        condition_scores=[ConditionScore(**score) for score in result["condition_scores"]],
        severity=result["severity"],
        see_doctor=bool(result["see_doctor"]),
        engine=str(result["engine"]),
        degraded=bool(result["degraded"]),
        disclaimer=DISCLAIMER,
        model_version=symptoms_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
