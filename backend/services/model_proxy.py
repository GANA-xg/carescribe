"""Model service proxy — thin HTTP client to FreeBuff's models:9000. OC-05+."""
import os

import httpx

MODEL_SERVICE_URL = os.getenv("MODEL_SERVICE_URL", "http://localhost:9000")


class ModelServiceError(Exception):
    """The internal model service failed or is unreachable."""


async def call_model(path: str, *, json_body: dict | None = None, content: bytes | None = None,
                    filename: str | None = None, timeout: float = 120) -> dict:
    """POST to the model service. Multipart when content is given, else JSON."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        if content is not None:
            files = {"file": (filename or "upload.bin", content)}
            resp = await client.post(f"{MODEL_SERVICE_URL}{path}", files=files)
        else:
            resp = await client.post(f"{MODEL_SERVICE_URL}{path}", json=json_body)
    if resp.status_code != 200:
        raise ModelServiceError(f"model service {path} -> {resp.status_code}: {resp.text[:200]}")
    return resp.json()
