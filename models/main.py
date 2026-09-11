"""CareScribe internal model service.

A FastAPI app that serves every model the backend needs, on port 9000. It is
**internal only**: it is not in the public port map of docker-compose and never
talks to the browser directly. The backend proxies to it.

Run locally::

    uvicorn main:app --host 0.0.0.0 --port 9000 --reload

Design notes
------------
* Models are resolved once, at startup, inside the lifespan handler (rule 2).
  The warmup runs on a daemon thread so the process starts accepting traffic
  immediately; ``/health`` reports each model as it becomes ready. Before the
  warmup finishes, ``models_loaded`` is simply empty, as FB-01 requires.
* A model that fails to load never stops the service. It is recorded as
  ``degraded`` or ``failed`` and surfaced by ``/health``.
* When ``WARMUP_ON_STARTUP=false`` nothing is preloaded and each model resolves
  on its first request instead — useful for fast test runs.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import get_settings
from routers import all_routers
from utils.errors import ModelServiceError
from utils.logging_db import get_log
from utils.registry import registry

logger = logging.getLogger("carescribe.models")


def _warmup_models() -> None:
    """Resolve every service's model, logging the outcome per service."""
    from services import all_services

    for service in all_services():
        try:
            outcome = service.warmup()
            logger.info("warmup %s: %s", service.name, outcome)
        except Exception as exc:  # noqa: BLE001 - one bad service must not stop the rest
            logger.warning("warmup %s raised: %s", service.name, exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    settings.ensure_dirs()
    initialised = get_log().initialise()
    logger.info(
        "%s v%s starting on %s:%s (device=%s, gpu=%s, inference_log=%s)",
        settings.service_name,
        settings.service_version,
        settings.host,
        settings.port,
        settings.device,
        settings.gpu_available,
        "ready" if initialised else "unavailable",
    )

    if settings.warmup_on_startup:
        # Non-blocking: /health answers with an empty model list until the
        # background thread finishes resolving each model.
        threading.Thread(
            target=_warmup_models,
            name="model-warmup",
            daemon=True,
        ).start()
    else:
        logger.info("startup warmup disabled; models will load on first request")

    yield

    logger.info("%s shutting down", settings.service_name)


def create_app() -> FastAPI:
    """Build the ASGI application. Importable by tests without side effects."""
    settings = get_settings()
    app = FastAPI(
        title="CareScribe Model Service",
        description=(
            "Internal model-serving API for CareScribe. Not exposed publicly; "
            "the backend calls it over the private network."
        ),
        version=settings.service_version,
        lifespan=lifespan,
    )

    @app.exception_handler(ModelServiceError)
    async def _model_service_error(_request: Request, exc: ModelServiceError) -> JSONResponse:
        """Return the contract's ``{error, message}`` shape, not ``{detail}``."""
        return JSONResponse(status_code=exc.status_code, content=exc.as_dict())

    for router in all_routers():
        app.include_router(router)

    @app.get("/", tags=["health"], summary="Service banner")
    def root() -> dict[str, Any]:
        return {
            "service": settings.service_name,
            "version": settings.service_version,
            "internal": True,
            "port": settings.port,
            "endpoints": sorted(
                route.path  # type: ignore[attr-defined]
                for route in app.routes
                if getattr(route, "path", "").startswith("/")
            ),
            "loaded_models": registry.loaded_keys(),
        }

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    import uvicorn

    _settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "main:app",
        host=_settings.host,
        port=_settings.port,
        log_level="info",
    )
