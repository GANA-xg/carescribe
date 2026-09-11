"""Symptom checker route. API contract: /symptoms/check. OC-10.

POST /symptoms/check — forwards symptoms to the model service and returns
{possible_conditions[], severity, see_doctor}. Rule from the contract:
see_doctor is ALWAYS true when severity == "high", regardless of what
the model said. Public endpoint (no PHI stored).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.model_proxy import ModelServiceError, call_model

router = APIRouter(prefix="/symptoms", tags=["symptoms"])


class SymptomCheckRequest(BaseModel):
    symptoms: list[str] = Field(min_length=1, max_length=30)


class SymptomCheckResponse(BaseModel):
    possible_conditions: list[dict]
    severity: str
    see_doctor: bool
    disclaimer: str = "This check is informational and not a diagnosis."


@router.post("/check", response_model=SymptomCheckResponse)
async def check(body: SymptomCheckRequest):
    """Rank possible conditions for a symptom list. Public."""
    try:
        raw = await call_model("/symptoms", json_body={"symptoms": body.symptoms})
    except ModelServiceError as e:
        raise HTTPException(502, f"Symptom model unavailable: {e}") from e

    # Map model output -> contract shape.
    conditions = raw.get("conditions") or []
    if conditions and isinstance(conditions[0], dict):
        possible = [
            {"name": c.get("name") or c.get("condition"), "score": c.get("score")}
            for c in conditions
        ]
    else:
        possible = [{"name": c, "score": None} for c in conditions]

    severity = raw.get("severity", "low")
    see_doctor = bool(raw.get("see_doctor", False)) or severity == "high"

    return SymptomCheckResponse(
        possible_conditions=possible,
        severity=severity,
        see_doctor=see_doctor,
    )
