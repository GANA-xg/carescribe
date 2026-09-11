"""``POST /stt`` — speech to text.

The backend feeds the returned transcript straight into the RAG assistant, so the
response also reports the detected language and a confidence the UI can use to
ask for confirmation when transcription was doubtful.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from schemas import SttResponse
from services.stt_service import SERVICE as stt_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms
from utils.transport import AUDIO_BODY, STT_FIELDS, STT_FORM_FIELDS, read_payload

router = APIRouter(tags=["stt"])


@router.post(
    "/stt",
    response_model=SttResponse,
    openapi_extra=AUDIO_BODY,
    summary="Transcribe speech",
)
async def transcribe(request: Request) -> SttResponse:
    # Accepts JSON {"audio_b64": ..., "language": "hi"} or a multipart upload
    # (field "audio_file" or "audio"); see utils/transport.py.
    payload = await read_payload(
        request, json_fields=STT_FIELDS, form_fields=STT_FORM_FIELDS, label="audio"
    )
    language = payload.fields.get("language")

    with InferenceTimer() as timer:
        result = stt_service.transcribe(
            payload.value, str(language) if language else None
        )

    record_inference(
        model_key=stt_service.serving_key,
        endpoint="/stt",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{result['duration_s']:.1f}s audio",
        confidence=float(result["confidence"]),
        degraded=bool(result["degraded"]),
    )

    return SttResponse(
        transcript=result["transcript"],
        language_detected=result["language_detected"],
        confidence=float(result["confidence"]),
        duration_s=float(result["duration_s"]),
        degraded=bool(result["degraded"]),
        note=result.get("note"),
        model_version=stt_service.model_version(),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
