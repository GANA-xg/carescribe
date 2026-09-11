"""``POST /tts`` — text to speech.

Returns base64 audio plus its container format. The contract says WAV, and Coqui
(offline) does return WAV; gTTS can only produce MP3, so ``audio_format`` states
which arrived rather than the caller discovering it from broken playback.
"""

from __future__ import annotations

from fastapi import APIRouter

from schemas import TtsRequest, TtsResponse
from services.tts_service import SERVICE as tts_service
from utils.logging_db import record_inference
from utils.timing import InferenceTimer, round_ms

router = APIRouter(tags=["tts"])


@router.post("/tts", response_model=TtsResponse, summary="Synthesise speech")
def synthesise(request: TtsRequest) -> TtsResponse:
    with InferenceTimer() as timer:
        result = tts_service.speak(request.text, request.language)

    record_inference(
        model_key=result["serving_key"],
        endpoint="/tts",
        inference_time_ms=timer.elapsed_ms,
        input_size=f"{len(request.text)} chars",
        confidence=None,
        degraded=bool(result["degraded"]),
    )

    return TtsResponse(
        audio_b64=result["audio_b64"],
        duration_s=float(result["duration_s"]),
        engine=str(result["engine"]),
        audio_format=result["audio_format"],
        degraded=bool(result["degraded"]),
        note=result.get("note"),
        model_version=str(result["model_version"]),
        inference_time_ms=round_ms(timer.elapsed_ms),
    )
