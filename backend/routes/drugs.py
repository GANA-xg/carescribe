"""Drug price / generics routes. API contract: /drugs/*. OC-09.

POST /drugs/compare          — {drug_names[]} -> brand vs generic + savings.
GET  /drugs/generics/{name}  — CDSCO/Jan Aushadhi generic alternatives.

Both public (no auth) — pricing data is not PHI.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services import drugs

router = APIRouter(prefix="/drugs", tags=["drugs"])


class CompareRequest(BaseModel):
    drug_names: list[str] = Field(min_length=1, max_length=20)


class CompareResponse(BaseModel):
    drugs: list[dict]


@router.post("/compare", response_model=CompareResponse)
async def compare(body: CompareRequest):
    """Fuzzy-match each drug name against the CDSCO/Jan Aushadhi CSV.

    Returns per-drug: brand price, generic alternative + price, savings.
    Unknown names come back as {name, found: false} — not an error.
    """
    return {"drugs": drugs.compare(body.drug_names)}


@router.get("/generics/{drug_name}")
async def generics(drug_name: str):
    """Generic alternatives for one drug (Jan Aushadhi pricing).

    404 when the drug cannot be matched at all.
    """
    results = drugs.generics_for(drug_name)
    if not results:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No match for '{drug_name}'")
    return {"generics": results}
