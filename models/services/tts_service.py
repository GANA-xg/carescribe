"""FB-10 — text to speech for the voice assistant.

Three tiers, in order:

1. **Coqui TTS** (``tts_models/en/ljspeech/tacotron2-DDC``) — offline neural TTS,
   returns 16-bit PCM WAV. Hindi uses ``tts_models/hi/cv/vits``.
2. **gTTS** — falls back to Google's online service; simpler, and needs network.
   It returns **MP3**, not WAV, so ``audio_format`` says which you got.
3. **Silent placeholder** — a valid WAV container of the right duration.

The placeholder exists so callers always receive a playable response with a
correct duration while the frontend is being built. It is silence, not a beep:
a tone in a clinical app would be mistaken for an alert. ``engine`` and
``degraded`` make it unmistakable that no speech was synthesised.
"""

from __future__ import annotations

import base64
import io
from typing import Any

from catalog import model_id
from config import get_settings
from utils.audio import float32_to_pcm16, pcm16_wav_b64, silence_wav_b64, wav_duration
from utils.loader import LazyModel

#: Seconds of silence produced per character by the placeholder, capped.
PLACEHOLDER_SECONDS_PER_CHAR = 0.06
PLACEHOLDER_MAX_SECONDS = 6.0

#: gTTS writes ~32 kbps mono MP3, which is about 4000 bytes per second.
MP3_BYTES_PER_SECOND = 4000

#: Coqui voice per language.
COQUI_MODELS: dict[str, str] = {
    "en": "tts_models/en/ljspeech/tacotron2-DDC",
    "hi": "tts_models/hi/cv/vits",
}
DEFAULT_LANGUAGE = "en"


class TtsService:
    """Synthesises speech, degrading to silence rather than failing."""

    name = "tts"
    endpoint = "/tts"

    def __init__(self) -> None:
        # Tier 1 -> tier 2. If both fail, load() raises and speak() uses tier 3.
        self._tts = LazyModel(
            "coqui_tts",
            self._load_coqui,
            fallback=self._load_gtts,
            fallback_key="gtts",
            note="Coqui offline TTS; gTTS online fallback; silent placeholder as last resort",
        )
        self.models = (self._tts,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_coqui() -> dict[str, Any]:
        """Load a Coqui model; raises so the loader falls through to gTTS."""
        from TTS.api import TTS as CoquiTts  # type: ignore[import-not-found]

        models: dict[str, Any] = {}
        errors: list[str] = []
        for language, model_name in COQUI_MODELS.items():
            try:
                models[language] = CoquiTts(model_name=model_name, progress_bar=False)
            except Exception as exc:  # noqa: BLE001 - try the next language
                errors.append(f"{model_name}: {exc}")
        if not models:
            raise RuntimeError("no Coqui TTS model could be loaded (" + "; ".join(errors) + ")")
        return {"engine": "coqui", "models": models}

    @staticmethod
    def _load_gtts() -> dict[str, Any]:
        """Fall back to the online gTTS service."""
        from gtts import gTTS  # type: ignore[import-not-found]

        return {"engine": "gtts", "module": gTTS}

    # --- introspection ----------------------------------------------------
    @property
    def engine(self) -> str:
        return "coqui" if self._tts.available else "gtts"

    @property
    def degraded(self) -> bool:
        return self._tts.serving_fallback

    def warmup(self) -> dict[str, bool]:
        return {self._tts.key: self._tts.warm()}

    @staticmethod
    def _credit(engine: str) -> dict[str, str]:
        """Attribution for whichever tier actually produced the audio.

        Which tier serves is decided per request (Coqui may exist but fail to
        synthesise, gTTS may have no network), so the version is reported by the
        tier that ran rather than guessed from load state.
        """
        key = {"coqui": "coqui_tts", "gtts": "gtts"}.get(engine, "tts_silent")
        return {"serving_key": key, "model_version": model_id(key)}

    # --- inference --------------------------------------------------------
    def speak(self, text: str, language: str | None = None) -> dict[str, Any]:
        """Synthesise ``text`` and return base64 audio."""
        language_code = (language or DEFAULT_LANGUAGE).lower()[:2]

        try:
            bundle = self._tts.load()
        except Exception:  # noqa: BLE001 - both real backends are unusable
            return self._placeholder(text, language_code, bundle=None)

        if bundle is None:
            return self._placeholder(text, language_code, bundle=None)

        if bundle["engine"] == "coqui":
            try:
                return self._speak_coqui(bundle, text, language_code)
            except Exception:  # noqa: BLE001 - degrade rather than 500
                return self._placeholder(text, language_code, bundle=bundle)

        try:
            return self._speak_gtts(bundle, text, language_code)
        except Exception:  # noqa: BLE001
            return self._placeholder(text, language_code, bundle=bundle)

    @staticmethod
    def _speak_coqui(
        bundle: dict[str, Any], text: str, language_code: str
    ) -> dict[str, Any]:
        """Synthesise WAV through the offline Coqui model."""
        import numpy as np

        engine = bundle["models"].get(language_code) or next(iter(bundle["models"].values()))
        audio = np.asarray(engine.tts(text=text), dtype=np.float32)

        sample_rate = 22050
        synthesizer = getattr(engine, "synthesizer", None)
        if synthesizer is not None:
            sample_rate = int(getattr(synthesizer, "output_sample_rate", sample_rate))

        audio_b64 = pcm16_wav_b64(float32_to_pcm16(audio), sample_rate)
        return {
            "audio_b64": audio_b64,
            "audio_format": "wav",
            "duration_s": wav_duration(base64.b64decode(audio_b64)),
            "engine": "coqui",
            "degraded": False,
            "note": None,
            **TtsService._credit("coqui"),
        }

    @staticmethod
    def _speak_gtts(
        bundle: dict[str, Any], text: str, language_code: str
    ) -> dict[str, Any]:
        """Synthesise MP3 through gTTS. Note the container is not WAV."""
        buffer = io.BytesIO()
        bundle["module"](text=text, lang=language_code).write_to_fp(buffer)
        payload = buffer.getvalue()
        if not payload:
            raise RuntimeError("gTTS returned no audio")

        return {
            "audio_b64": base64.b64encode(payload).decode("ascii"),
            "audio_format": "mp3",
            "duration_s": round(len(payload) / MP3_BYTES_PER_SECOND, 3),
            "engine": "gtts",
            "degraded": True,
            "note": (
                "gTTS returns MP3, not WAV; duration is estimated from the bitrate. "
                "Install Coqui TTS for WAV output."
            ),
            **TtsService._credit("gtts"),
        }

    @staticmethod
    def _placeholder(text: str, language_code: str, bundle: Any) -> dict[str, Any]:
        """Silent WAV of plausible length, clearly marked as synthesised nothing."""
        duration = min(
            PLACEHOLDER_MAX_SECONDS,
            max(0.5, len(text) * PLACEHOLDER_SECONDS_PER_CHAR),
        )
        return {
            "audio_b64": silence_wav_b64(duration),
            "audio_format": "wav",
            "duration_s": round(duration, 3),
            "engine": "silent",
            "degraded": True,
            "note": (
                "no TTS backend available; returning silence. Install Coqui TTS "
                "(`pip install TTS`) for offline speech, or gTTS for online speech."
            ),
            **TtsService._credit("silent"),
        }


SERVICE = TtsService()
