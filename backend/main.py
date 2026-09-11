"""CareScribe backend entrypoint.

Serves the API contract at :8000. Routers are registered as they are
built (auth OC-03, ocr OC-05, imaging OC-06, faceid OC-07, ...).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="CareScribe API",
    version="0.1.0",
    description="AI health passport for rural India — backend.",
)

# OC-14 will tighten this to env-configured origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routes import health  # noqa: E402  (import after app defined)

app.include_router(health.router)


@app.get("/health")
def health_root():
    """Container healthcheck endpoint — public."""
    return {"status": "ok", "service": "backend"}
