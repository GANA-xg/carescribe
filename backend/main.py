"""CareScribe backend entrypoint.

Serves the API contract at :8000. Routers are registered as they are
built (auth OC-03, ocr OC-05, imaging OC-06, faceid OC-07, ...).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("carescribe.main")


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

# OC-14 will tighten this to env-configured origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import auth, faceid, health, imaging, ocr, passport  # noqa: E402

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ocr.router)
app.include_router(imaging.router)
app.include_router(faceid.router)
app.include_router(passport.router)


@app.get("/health")
def health_root():
    """Container healthcheck endpoint — public."""
    return {"status": "ok", "service": "backend"}
