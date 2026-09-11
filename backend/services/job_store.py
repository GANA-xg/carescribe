"""OCR job store — Redis-backed (falls back to in-memory dict for tests)."""
import json
import os

import redis.asyncio as aioredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

JOB_TTL = 3600  # results expire after 1h

_memory: dict[str, dict] = {}  # in-memory fallback
_client = None


async def _redis():
    global _client
    if _client is None:
        _client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def set_job(job_id: str, payload: dict) -> None:
    """Store job state. Uses Redis when reachable; falls back to memory."""
    try:
        await (await _redis()).set(f"ocr:job:{job_id}", json.dumps(payload), ex=JOB_TTL)
    except Exception:
        _memory[job_id] = payload


async def get_job(job_id: str) -> dict | None:
    """Fetch job state, or None if unknown/expired."""
    try:
        raw = await (await _redis()).get(f"ocr:job:{job_id}")
    except Exception:
        return _memory.get(job_id)
    if raw is None:
        return _memory.get(job_id)
    return json.loads(raw)
