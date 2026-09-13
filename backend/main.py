"""CareScribe backend entrypoint — hardened. OC-14.

Security posture:
  * Rate limiting (slowapi): 10/min on auth, 30/min everywhere else.
  * CORS: env-configured (CORS_ORIGINS), localhost:3000 default.
  * Upload size cap: 10MB enforced per-route at read time.
  * JWT: JWT_SECRET env; /auth/refresh rotates tokens.
  * Startup fails closed when JWT_SECRET is the dev default in prod.
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from starlette.middleware.base import BaseHTTPMiddleware

from rate_limit import limiter

logger = logging.getLogger("carescribe.main")

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

if ENVIRONMENT == "production" and JWT_SECRET == "dev-secret-change-me":
    raise RuntimeError("JWT_SECRET must be set to a real secret in production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: seed Orthanc + build the FAISS face index. Shutdown: dispose engine."""
    from services import dicom_seed, faceid

    await dicom_seed.seed_orthanc()
    await faceid.rebuild_index()
    yield
    import database

    if database._engine is not None:
        await database._engine.dispose()


app = FastAPI(
    title="CareScribe API",
    version="0.1.0",
    description="AI health passport for rural India — backend.",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=3600,
)

MAX_BODY_BYTES = 10 * 1024 * 1024  # 10MB — applies to all requests


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they're read.

    Returns a raw JSONResponse: HTTPException isn't handled when raised
    from middleware (FastAPI handlers only wrap route exceptions).
    """

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=413,
                content={"detail": "Request too large (10MB max)"},
            )
        return await call_next(request)


app.add_middleware(BodySizeLimitMiddleware)

from routes import (  # noqa: E402
    assistant,
    auth,
    clinical,
    diagnosis,
    drugs,
    faceid,
    health,
    imaging,
    ocr,
    patients,
    passport,
    symptoms,
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ocr.router)
app.include_router(imaging.router)
app.include_router(faceid.router)
app.include_router(passport.router)
app.include_router(drugs.router)
app.include_router(symptoms.router)
app.include_router(clinical.router)
app.include_router(assistant.router)
app.include_router(diagnosis.router)
app.include_router(patients.router)


@app.get("/health")
def health_root():
    """Container healthcheck endpoint — public, rate limited with the rest."""
    return {"status": "ok", "service": "backend"}
