"""``POST /embed`` — batch text embeddings for the backend's RAG index.

The backend calls this when indexing passport records and again on each query.
Vectors are L2-normalised, so cosine similarity is a plain dot product and the
backend can use any FAISS index type without renormalising.
"""

from __future__ import annotations

from fastapi import APIRouter

from schemas import EmbedRequest, EmbedResponse
from services.embed_service import SERVICE as embed_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms

router = APIRouter(tags=["embed"])


@router.post("/embed", response_model=EmbedResponse, summary="Batch text embeddings")
def embed(request: EmbedRequest) -> EmbedResponse:
    with InferenceTimer() as timer:
        result = embed_service.embed(request.texts)

    record_inference(
        model_key=embed_service.serving_key,
        endpoint="/embed",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{len(request.texts)} texts",
        confidence=None,
        degraded=bool(result["degraded"]),
    )

    return EmbedResponse(
        embeddings=result["embeddings"],
        model=embed_service.model_version(),
        dim=result["dim"],
        degraded=bool(result["degraded"]),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
