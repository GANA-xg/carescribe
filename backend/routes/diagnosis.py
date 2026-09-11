"""Diagnosis comparator. API contract: /diagnosis/compare. OC-13.

POST /diagnosis/compare — map two diagnoses to ICD-10 codes, compute
agreement (exact code match or embedding cosine via pgvector), explain.
Public — the two diagnoses are compared in isolation (no PHI stored).
"""
import csv
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from database import SessionLocal
from services import rag

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])

CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "icd10.csv")

_icd: list[tuple[str, str]] = []

SIM_THRESHOLD = 0.75  # cosine similarity counts as "same family"


def load_icd() -> None:
    """Load the ICD-10 subset CSV once at startup."""
    global _icd
    _icd = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            _icd.append((row["code"].strip(), row["description"].strip().lower()))


load_icd()


def map_to_icd(diagnosis: str) -> tuple[str | None, float]:
    """Best ICD code for a diagnosis text (exact then fuzzy)."""
    from difflib import get_close_matches

    d = diagnosis.strip().lower()
    # exact description hit
    for code, desc in _icd:
        if d == desc:
            return code, 1.0
    # code itself given
    up = diagnosis.strip().upper()
    for code, desc in _icd:
        if up == code:
            return code, 1.0
    # fuzzy over descriptions
    descs = [desc for _, desc in _icd]
    close = get_close_matches(d, descs, n=1, cutoff=0.6)
    if close:
        for code, desc in _icd:
            if desc == close[0]:
                return code, 0.6
    return None, 0.0


class CompareDiagnosisRequest(BaseModel):
    diagnosis_a: str = Field(min_length=1, max_length=500)
    diagnosis_b: str = Field(min_length=1, max_length=500)
    date_a: str | None = None
    date_b: str | None = None


@router.post("/compare")
async def compare(body: CompareDiagnosisRequest):
    """Compare two diagnoses: ICD mapping + embedding similarity.

    Agreement = exact ICD code match OR cosine >= 0.75. The explanation
    says which rule fired, so doctors see WHY the system agrees/disagrees.
    """
    code_a, a_exact = map_to_icd(body.diagnosis_a)
    code_b, b_exact = map_to_icd(body.diagnosis_b)

    # Embedding cosine via the same embedder the RAG store uses.
    vec_a = await rag.embed(body.diagnosis_a)
    vec_b = await rag.embed(body.diagnosis_b)
    dot = sum(x * y for x, y in zip(vec_a, vec_b))
    norm_a = sum(x * x for x in vec_a) ** 0.5 or 1.0
    norm_b = sum(x * x for x in vec_b) ** 0.5 or 1.0
    cosine = dot / (norm_a * norm_b)

    codes = [c for c in (code_a, code_b) if c]
    agreement = bool(
        (code_a and code_a == code_b) or cosine >= SIM_THRESHOLD
    )

    if code_a and code_a == code_b:
        reason = f"Both map to ICD-10 {code_a} — same diagnosis."
    elif agreement:
        reason = (
            f"Different ICD codes ({code_a} vs {code_b}) but embedding similarity "
            f"{cosine:.2f} is above {SIM_THRESHOLD} — clinically close."
        )
    else:
        reason = (
            f"ICD codes differ ({code_a or 'unmapped'} vs {code_b or 'unmapped'}) "
            f"and embedding similarity {cosine:.2f} is below {SIM_THRESHOLD}."
        )

    return {
        "agreement": agreement,
        "conflict_details": None if agreement else reason,
        "icd_codes": codes,
        "explanation": reason,
        "similarity": round(cosine, 4),
    }
