"""Audio decoding and encoding helpers for the STT and TTS endpoints.

Speech requests arrive as base64 blobs (WAV / MP3 / OGG) and replies go back as
base64 WAV, so both directions funnel through here. WAV writing uses only the
standard library, which keeps the TTS placeholder path dependency-free.
"""

from __future__ import annotations

import base64
import binascii
import io
import wave

from utils.errors import bad_audio

MAX_AUDIO_BYTES = 30 * 1024 * 1024  # ~30s of 16 kHz mono is tiny; this is generous.

_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"RIFF", "wav"),
    (b"ID3", "mp3"),
    (b"OggS", "ogg"),
    (b"fLaC", "flac"),
    (b"\x1aE\xdf\xa3", "webm"),
)


def decode_b64_audio(audio_b64: str) -> bytes:
    """Decode a base64 audio blob, tolerating missing padding."""
    if not isinstance(audio_b64, str):
        raise bad_audio("audio payload must be a base64 string")
    cleaned = "".join(audio_b64.split())
    if cleaned.startswith("data:") and "," in cleaned:
        cleaned = cleaned.split(",", 1)[1]
    if not cleaned:
        raise bad_audio("empty audio payload")
    padding = (-len(cleaned)) % 4
    try:
        data = base64.b64decode(cleaned + "=" * padding, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise bad_audio(f"base64 decode failed: {exc}") from exc
    if not data:
        raise bad_audio("decoded audio is empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise bad_audio(f"audio too large ({len(data)} bytes)")
    return data


def sniff_format(data: bytes) -> str:
    """Guess the container from its magic bytes; ``"unknown"`` when unsure."""
    for signature, name in _SIGNATURES:
        if data.startswith(signature):
            return name
    # Bare MP3 frames start with 0xFF Ex.
    if len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return "mp3"
    return "unknown"


def silence_wav_b64(duration_s: float = 1.0, sample_rate: int = 16000) -> str:
    """Encode silence as a valid base64 WAV.

    The TTS placeholder returns this so callers always receive a playable
    container of the right duration. A tone would be mistaken for a clinical
    alert, and random noise would sound like corruption — silence reads as
    "no speech available", which is exactly what it means.
    """
    frames = max(1, int(duration_s * sample_rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)  # 16-bit PCM
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def pcm16_wav_b64(samples: bytes, sample_rate: int, channels: int = 1) -> str:
    """Wrap raw signed 16-bit PCM in a WAV container and base64-encode it."""
    if not samples:
        return silence_wav_b64(0.25, sample_rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(samples)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def wav_duration(data: bytes) -> float:
    """Duration in seconds of a WAV byte string, or ``0.0`` if unreadable."""
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            rate = handle.getframerate() or 1
            return round(handle.getnframes() / float(rate), 3)
    except Exception:  # noqa: BLE001
        return 0.0


def duration_b64(audio_b64: str) -> float:
    """Best-effort duration of a base64 payload; never raises."""
    try:
        return wav_duration(decode_b64_audio(audio_b64))
    except Exception:  # noqa: BLE001
        return 0.0


def float32_to_pcm16(samples: object) -> bytes:
    """Convert float samples in ``[-1, 1]`` to signed 16-bit little-endian PCM."""
    import numpy as np

    array = np.asarray(samples, dtype=np.float32).reshape(-1)
    clipped = np.clip(array, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def resample_linear(samples: object, source_rate: int, target_rate: int) -> object:
    """Cheap linear resampling; adequate for 16 kHz speech models."""
    import numpy as np

    array = np.asarray(samples, dtype=np.float32).reshape(-1)
    if source_rate == target_rate or array.size == 0:
        return array
    target_length = max(1, int(round(array.size * target_rate / float(source_rate))))
    source_positions = np.linspace(0.0, 1.0, num=array.size, endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, array).astype(np.float32)


def wav_to_float32(data: bytes, target_rate: int = 16000) -> tuple[object, int]:
    """Decode PCM WAV bytes to mono float32 at ``target_rate``.

    Returns ``(samples, sample_rate)``. Only PCM WAV is supported natively; the
    Whisper backend handles compressed formats through its own decoder.
    """
    import numpy as np

    with wave.open(io.BytesIO(data), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.readframes(handle.getnframes())

    if width != 2:
        raise bad_audio(f"unsupported WAV sample width: {width * 8}-bit (expected 16-bit)")

    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return resample_linear(samples, rate, target_rate), target_rate


__all__ = [
    "MAX_AUDIO_BYTES",
    "decode_b64_audio",
    "sniff_format",
    "silence_wav_b64",
    "pcm16_wav_b64",
    "wav_duration",
    "duration_b64",
    "float32_to_pcm16",
    "resample_linear",
    "wav_to_float32",
]
