"""FB-09 and FB-10 tests — the ``/stt`` and ``/tts`` contracts.

Neither Whisper nor Coqui is installed in a default test run, so what is asserted
is the honest-degradation contract: an empty transcript rather than an invented
one, and silence rather than a fabricated voice.
"""

from __future__ import annotations

import base64

import pytest

from utils.audio import decode_b64_audio, sniff_format, wav_duration


class TestSttEndpoint:
    def test_returns_an_empty_transcript_rather_than_inventing_one(
        self, client, wav_b64
    ) -> None:
        response = client.post("/stt", json={"audio_b64": wav_b64})
        assert response.status_code == 200
        body = response.json()

        assert body["transcript"] == ""
        assert body["confidence"] == 0.0
        assert body["degraded"] is True
        assert "faster-whisper" in body["note"]

    def test_reports_version_latency_and_duration(self, client, wav_b64) -> None:
        body = client.post("/stt", json={"audio_b64": wav_b64}).json()
        assert body["model_version"] == "whisper-base-v1.0"
        assert body["inference_time_ms"] >= 0.0
        assert body["duration_s"] == pytest.approx(1.0, abs=0.05)

    def test_language_is_reported_as_unknown_when_unavailable(self, client, wav_b64) -> None:
        body = client.post("/stt", json={"audio_b64": wav_b64, "language": "hi"}).json()
        assert body["language_detected"] is None

    def test_rejects_a_non_audio_payload(self, client) -> None:
        # A PNG's bytes are not decodable as the expected container signature,
        # but base64 decoding still succeeds; validity is judged by the backend.
        response = client.post("/stt", json={"audio_b64": "!!not base64!!"})
        assert response.status_code == 400
        assert response.json()["error"] in {"invalid_audio", "model_unavailable"}

    def test_rejects_an_empty_payload(self, client) -> None:
        assert client.post("/stt", json={"audio_b64": ""}).status_code == 422

    def test_rejects_a_missing_field(self, client) -> None:
        assert client.post("/stt", json={}).status_code == 422

    def test_inference_is_logged(self, client, wav_b64, isolated_log) -> None:
        client.post("/stt", json={"audio_b64": wav_b64})
        summary = isolated_log.per_model_summary()
        assert any(row["model_key"] == "whisper" for row in summary)


class TestTtsPlaceholderTier:
    def test_returns_playable_silence_when_no_backend_exists(self, client) -> None:
        response = client.post("/tts", json={"text": "Take one tablet daily"})
        assert response.status_code == 200
        body = response.json()

        assert body["engine"] == "silent"
        assert body["audio_format"] == "wav"
        assert body["degraded"] is True
        assert "TTS" in body["note"]

        # The payload must be a genuinely valid WAV, not just a placeholder string.
        data = decode_b64_audio(body["audio_b64"])
        assert sniff_format(data) == "wav"
        assert wav_duration(data) > 0.0

    def test_duration_tracks_text_length(self, client) -> None:
        short = client.post("/tts", json={"text": "Hi"}).json()["duration_s"]
        long = client.post(
            "/tts", json={"text": "Take one tablet twice daily after food for five days."}
        ).json()["duration_s"]
        assert long >= short

    def test_duration_is_capped(self, client) -> None:
        body = client.post("/tts", json={"text": "word " * 500}).json()
        assert body["duration_s"] <= 6.0

    def test_reported_duration_matches_the_audio(self, client) -> None:
        body = client.post("/tts", json={"text": "Take one tablet daily"}).json()
        actual = wav_duration(decode_b64_audio(body["audio_b64"]))
        assert actual == pytest.approx(body["duration_s"], abs=0.05)

    def test_returns_valid_base64(self, client) -> None:
        body = client.post("/tts", json={"text": "Hello"}).json()
        base64.b64decode(body["audio_b64"])
        assert body["model_version"] == "tts-silent-v1.0"

    def test_rejects_empty_text(self, client) -> None:
        assert client.post("/tts", json={"text": ""}).status_code == 422

    def test_rejects_overlong_text(self, client) -> None:
        assert client.post("/tts", json={"text": "x" * 5001}).status_code == 422

    def test_accepts_a_hindi_language_code(self, client) -> None:
        body = client.post("/tts", json={"text": "namaste", "language": "hi"}).json()
        assert body["engine"] == "silent"

    def test_inference_is_logged(self, client, isolated_log) -> None:
        client.post("/tts", json={"text": "Hello"})
        summary = isolated_log.per_model_summary()
        assert any(row["model_key"] == "tts_silent" for row in summary)


@pytest.mark.heavy
class TestRealSpeechBackends:
    def test_whisper_transcribes(self, client, wav_b64) -> None:
        from services.stt_service import SERVICE

        if not SERVICE.available and not SERVICE._model.warm():
            pytest.skip("no speech-to-text backend installed")

        body = client.post("/stt", json={"audio_b64": wav_b64}).json()
        assert body["degraded"] is False

    def test_coqui_or_gtts_synthesises(self, client) -> None:
        from services.tts_service import SERVICE

        if not SERVICE._tts.warm():
            pytest.skip("neither Coqui TTS nor gTTS is installed")

        body = client.post("/tts", json={"text": "Take one tablet daily"}).json()
        assert body["engine"] in {"coqui", "gtts"}
        assert decode_b64_audio(body["audio_b64"])
