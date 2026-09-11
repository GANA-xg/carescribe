"""``GET /health`` — liveness plus a full model inventory.

FB-01 only requires ``{status, models_loaded, gpu}`` and demands that the
endpoint answer *during* startup, before any model has loaded. FB-12 then asks
for every loaded model's version and load time. Both are satisfied here:
``models_loaded`` stays a simple list of keys, and ``models`` carries the
per-model detail.

The endpoint never raises. A health check that fails when the service is sick
is useless.

``status`` is ``degraded`` whenever any model is serving a fallback, so an
orchestrator can tell "up but running on fallbacks" from "fully warm".
"""

from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from schemas import HealthResponse
from utils.registry import registry

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service and model health")
def health() -> HealthResponse:
    settings = get_settings()
    snapshot = registry.snapshot()
    serving = [item["key"] for item in snapshot if item["serving"]]
    degraded = [item["key"] for item in snapshot if item["status"] == "degraded"]
    return HealthResponse(
        status="degraded" if degraded else "ok",
        models_loaded=serving,
        models=snapshot,
        gpu=settings.gpu_available,
        device=settings.device,
        service_version=settings.service_version,
        degraded_models=degraded,
    )
