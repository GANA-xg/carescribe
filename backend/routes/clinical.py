"""Clinical decision support routes. API contract: /clinical/*. OC-11.

POST /clinical/sepsis-risk — doctor-only. Validates vitals, calls the
model service, returns risk score + SHAP explanation + trend. The result
is also written to the patient's HealthRecord (type=sepsis_score).
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_doctor
from database import get_db
from models.db import Doctor, User
from services.model_proxy import ModelServiceError, call_model

router = APIRouter(prefix="/clinical", tags=["clinical"])


class Vitals(BaseModel):
    temp: float = Field(gt=25, lt=45, description="Body temperature, Celsius")
    hr: float = Field(gt=20, lt=300, description="Heart rate, bpm")
    rr: float = Field(gt=4, lt=80, description="Respiratory rate, breaths/min")
    wbc: float = Field(ge=0, lt=200, description="White cell count, 10^3/uL")
    lactate: float = Field(ge=0, lt=30, description="Serum lactate, mmol/L")


class SepsisRiskRequest(BaseModel):
    patient_id: uuid.UUID
    vitals: Vitals


class ShapItem(BaseModel):
    feature: str
    value: float


class SepsisRiskResponse(BaseModel):
    risk_score: float
    risk_level: str
    shap_explanation: list[ShapItem] = []
    trend: list = []
    explanation: str = ""
    record_id: Optional[uuid.UUID] = None


@router.post("/sepsis-risk", response_model=SepsisRiskResponse)
async def sepsis_risk(
    body: SepsisRiskRequest,
    doctor: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """Score sepsis risk from five vitals. DOCTOR-ONLY.

    The score + explanation are saved to the patient's HealthRecord so
    the passport and RAG assistant can cite them later.
    """
    try:
        raw = await call_model(
            "/sepsis-risk",
            json_body={"vitals": body.vitals.model_dump()},
        )
    except ModelServiceError as e:
        raise HTTPException(502, f"Sepsis model unavailable: {e}") from e

    shap = [
        ShapItem(feature=item.get("feature", ""), value=item.get("value", 0.0))
        for item in raw.get("shap_values", [])
    ]

    # Persist to HealthRecord (best effort — a DB hiccup must not lose
    # the live score the doctor is looking at).
    record_id = None
    try:
        from models.db import HealthRecord

        rec = HealthRecord(
            patient_id=body.patient_id,
            type="sepsis_score",
            source="manual",
            data={
                "risk_score": raw.get("risk_score"),
                "risk_level": raw.get("risk_level"),
                "vitals": body.vitals.model_dump(),
                "explanation": raw.get("explanation", ""),
                "shap": [s.model_dump() for s in shap],
                "scored_by_doctor": str(doctor.id),
            },
        )
        db.add(rec)
        await db.commit()
        await db.refresh(rec)
        record_id = rec.id
    except Exception:
        await db.rollback()

    return SepsisRiskResponse(
        risk_score=raw.get("risk_score", 0.0),
        risk_level=raw.get("risk_level", "low"),
        shap_explanation=shap,
        trend=raw.get("trend", []),
        explanation=raw.get("explanation", ""),
        record_id=record_id,
    )
