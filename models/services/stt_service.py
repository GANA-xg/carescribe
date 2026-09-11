"""FB-09 — speech to text for the voice assistant.

Primary backend: ``faster-whisper`` (CTranslate2), which is roughly 4x faster than
the reference implementation on CPU and reports a real per-segment log
probability we turn into a confidence. Secondary: the ``transformers`` Whisper
pipeline, which needs no extra runtime but reports no confidence.

**No fabricated transcript.** With neither backend installed the service returns
an empty transcript, ``confidence 0`` and ``degraded`` true. Inventing plausible
clinical speech would be far worse than admitting the model is absent, and rules
3 and 6 both point the same way.

Language detection is automatic when the caller omits ``language``; the brief's
Hindi support falls out of Whisper's own multilingual training, and a
Hindi-specific checkpoint can be dropped in by setting ``WHISPER_MODEL``.
"""

from __future__ import annotations

import io
import math
import os
from typing import Any

from catalog import model_id
from config import get_settings
from utils.audio import decode_b64_audio, sniff_format, wav_to_float32, wav_duration
from utils.confidence import normalize_confidence
from utils.loader import LazyModel

#: Whisper checkpoint to load; override for Hindi or a larger model.
DEFAULT_WHISPER_MODEL = "openai/whisper-base"

#: Sample rate Whisper expects.
TARGET_RATE = 16000

#: Formats the transformers backend cannot decode without extra audio libraries.
TRANSFORMERS_FORMATS = {"wav"}


class SttService:
    """Transcribes speech with automatic language detection."""

    name = "stt"
    endpoint = "/stt"

    def __init__(self) -> None:
        # fallback=lambda: None marks the model degraded rather than failed, so
        # /health distinguishes "Whisper missing" from "the service is broken".
        self._model = LazyModel(
            "whisper",
            self._load_whisper,
            fallback=lambda: None,
            note="Whisper transcription; empty results are returned when unavailable",
        )
        self.models = (self._model,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_whisper() -> dict[str, Any]:
        """Load faster-whisper if present, else the transformers pipeline."""
        model_name = os.getenv("WHISPER_MODEL", DEFAULT_WHISPER_MODEL)

        try:
            from faster_whisper import WhisperModel

            return {
                "backend": "faster-whisper",
                "model": WhisperModel(model_name, device="cpu", compute_type="int8"),
                "model_name": model_name,
            }
        except ImportError:
            pass

        try:
            from transformers import pipeline

            return {
                "backend": "transformers",
                "model": pipeline(
                    "automatic-speech-recognition",
                    model=model_name,
                ),
                "model_name": model_name,
            }
        except ImportError as exc:
            raise RuntimeError(
                "no speech-to-text backend available; install faster-whisper "
                "(pip install faster-whisper) or transformers"
            ) from exc

    # --- introspection ----------------------------------------------------
    @property
    def available(self) -> bool:
        return self._model.available

    @property
    def serving_key(self) -> str:
        return "whisper"

    def model_version(self) -> str:
        return model_id("whisper")

    @property
    def backend(self) -> str:
        if not self.available:
            return "unavailable"
        return str(self._model.load().get("backend", "unknown"))

    def warmup(self) -> dict[str, bool]:
        return {self._model.key: self._model.warm()}

    # --- inference --------------------------------------------------------
    def transcribe(self, audio_b64: str, language: str | None = None) -> dict[str, Any]:
        """Transcribe a base64 audio blob, detecting the language by default."""
        data = decode_b64_audio(audio_b64)
        audio_format = sniff_format(data)
        duration = wav_duration(data)

        self._model.load()
        if not self.available:
            return {
                "transcript": "",
                "language_detected": None,
                "confidence": 0.0,
                "duration_s": duration,
                "backend": "unavailable",
                "degraded": True,
                "note": (
                    "speech-to-text backend unavailable; install faster-whisper to "
                    "enable transcription"
                ),
            }

        bundle = self._model.load()
        if bundle["backend"] == "faster-whisper":
            result = self._transcribe_faster_whisper(bundle, data, language)
        else:
            result = self._transcribe_transformers(bundle, data, audio_format, language)

        result["duration_s"] = duration
        result["degraded"] = False
        return result

    @staticmethod
    def _transcribe_faster_whisper(
        bundle: dict[str, Any], data: bytes, language: str | None
    ) -> dict[str, Any]:
        """Transcribe via CTranslate2; segments carry a real log probability."""
        segments, info = bundle["model"].transcribe(
            io.BytesIO(data),
            language=language,
            beam_size=5,
            vad_filter=True,
        )

        texts: list[str] = []
        log_probabilities: list[float] = []
        for segment in segments:
            text = (segment.text or "").strip()
            if text:
                texts.append(text)
                log_probabilities.append(float(getattr(segment, "avg_logprob", 0.0)))

        transcript = " ".join(texts).strip()
        # exp(mean avg_logprob) is the standard sequence-level confidence.
        confidence = (
            normalize_confidence(math.exp(sum(log_probabilities) / len(log_probabilities)))
            if log_probabilities
            else 0.0
        )

        return {
            "transcript": transcript,
            "language_detected": getattr(info, "language", None) or language,
            "confidence": confidence,
            "backend": "faster-whisper",
            "note": None,
        }

    @staticmethod
    def _transcribe_transformers(
        bundle: dict[str, Any],
        data: bytes,
        audio_format: str,
        language: str | None,
    ) -> dict[str, Any]:
        """Transcribe via the transformers pipeline.

        Only PCM WAV can be decoded without extra audio libraries, and the
        pipeline exposes no confidence, so both limitations are reported rather
        than papered over.
        """
        if audio_format not in TRANSFORMERS_FORMATS:
            return {
                "transcript": "",
                "language_detected": language,
                "confidence": 0.0,
                "backend": "transformers",
                "degraded": True,
                "note": (
                    f"the transformers backend cannot decode {audio_format!r} audio "
                    "without extra libraries; send WAV or install faster-whisper"
                ),
            }

        samples, _rate = wav_to_float32(data, TARGET_RATE)
        generate_kwargs = {"language": language} if language else {}
        output = bundle["model"](
            {"array": samples, "sampling_rate": TARGET_RATE},
            generate_kwargs=generate_kwargs,
        )
        transcript = (output.get("text") or "").strip() if isinstance(output, dict) else ""

        return {
            "transcript": transcript,
            "language_detected": language,
            "confidence": 0.0,
            "backend": "transformers",
            "note": (
                "the transformers backend does not report a confidence or a detected "
                "language; install faster-whisper for both"
            ),
        }


SERVICE = SttService()
