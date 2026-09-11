"""``POST /sepsis-risk`` — doctor-only sepsis risk scoring.

Called by the backend from the clinician dashboard; the backend is responsible
for enforcing the doctor role, since this internal service has no notion of the
requesting user.
"""

from __future__ import annotations

from fastapi import APIRouter

from schemas import SepsisRequest, SepsisResponse, ShapValue
from services.sepsis_service import SERVICE as sepsis_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms

router = APIRouter(tags=["sepsis"])


@router.post(
    "/sepsis-risk",
    response_model=SepsisResponse,
    summary="Score sepsis onset risk from five vitals",
)
def sepsis_risk(request: SepsisRequest) -> SepsisResponse:
    vitals = request.vitals.model_dump()

    with InferenceTimer() as timer:
        result = sepsis_service.score(vitals)

    record_inference(
        model_key=sepsis_service.serving_key,
        endpoint="/sepsis-risk",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{len(vitals)} vitals",
        confidence=result["risk_score"] / 100.0,
        degraded=bool(result["degraded"]),
    )

    return SepsisResponse(
        risk_score=result["risk_score"],
        risk_level=result["risk_level"],
        shap_values=[ShapValue(**item) for item in result["shap_values"]],
        explanation=result["explanation"],
        explanation_method=result["explanation_method"],
        engine=str(result["engine"]),
        degraded=bool(result["degraded"]),
        model_version=sepsis_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
