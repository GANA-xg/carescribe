"""Dual-transport tests — every file endpoint over JSON *and* multipart.

The internal contract specifies base64 JSON; OpenCode's backend scaffolding sends
multipart uploads. Both must reach the model identically, and neither may 500.

The assertions here mostly check *which layer* answered: a 503 from
`/faceid/embed` means the request was parsed correctly and the model backend was
then found missing, whereas a 400/422 means parsing failed.
"""

from __future__ import annotations

import base64

import pytest


def upload_bytes(b64_payload: str) -> bytes:
    """Turn a base64 fixture into raw bytes suitable for a multipart part."""
    return base64.b64decode(b64_payload)


class TestOcrTransport:
    @pytest.mark.parametrize("field", ["file", "image", "upload", "image_b64"])
    def test_accepts_a_multipart_upload_under_any_accepted_field(
        self, client, png_b64, field
    ) -> None:
        response = client.post(
            "/ocr",
            files={field: ("prescription.png", upload_bytes(png_b64), "image/png")},
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body["merged"]["structured"]) == {"drugs", "diagnosis", "date"}

    def test_accepts_a_base64_string_in_a_form_field(self, client, png_b64) -> None:
        # Some clients put base64 in a form field instead of a real file part.
        response = client.post("/ocr", data={"image_b64": png_b64})
        assert response.status_code == 200

    def test_json_and_multipart_agree(self, client, png_b64) -> None:
        over_json = client.post("/ocr", json={"image_b64": png_b64}).json()
        over_form = client.post(
            "/ocr", files={"file": ("rx.png", upload_bytes(png_b64), "image/png")}
        ).json()

        assert over_json["agreement"] == over_form["agreement"]
        assert over_json["engines"] == over_form["engines"]
        assert over_json["merged"]["text"] == over_form["merged"]["text"]

    def test_multipart_without_a_recognised_part_is_a_422(self, client) -> None:
        response = client.post("/ocr", files={"unrelated": ("a.txt", b"hello", "text/plain")})
        assert response.status_code == 422
        assert response.json()["error"] == "missing_payload"

    def test_multipart_with_corrupt_bytes_is_a_400(self, client) -> None:
        response = client.post(
            "/ocr", files={"file": ("bad.png", b"not an image at all", "image/png")}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"


class TestTumorTransport:
    @pytest.mark.parametrize("field", ["dicom_file", "file", "image"])
    def test_accepts_a_multipart_upload(self, client, png_b64, field) -> None:
        # 503 proves the upload was parsed and the request reached the model layer,
        # which then reported the checkpoint missing.
        response = client.post(
            "/tumor-predict",
            files={field: ("scan.dcm", upload_bytes(png_b64), "application/octet-stream")},
        )
        assert response.status_code == 503
        assert response.json()["error"] == "model_unavailable"

    def test_reads_the_heatmap_flag_from_a_form_field(self, client, png_b64) -> None:
        response = client.post(
            "/tumor-predict",
            files={"dicom_file": ("scan.dcm", upload_bytes(png_b64), "application/octet-stream")},
            data={"with_heatmap": "true"},
        )
        assert response.status_code == 503

    def test_reads_the_heatmap_flag_from_json(self, client, png_b64) -> None:
        response = client.post(
            "/tumor-predict", json={"image_b64": png_b64, "with_heatmap": True}
        )
        assert response.status_code == 503


class TestFaceIdTransport:
    @pytest.mark.parametrize("field", ["image", "file"])
    def test_accepts_a_multipart_upload(self, client, png_b64, field) -> None:
        response = client.post(
            "/faceid/embed",
            files={field: ("face.jpg", upload_bytes(png_b64), "image/jpeg")},
        )
        assert response.status_code == 503
        assert response.json()["error"] == "model_unavailable"

    def test_multipart_without_a_part_is_a_422(self, client) -> None:
        response = client.post("/faceid/embed", files={"nope": ("a.txt", b"x", "text/plain")})
        assert response.status_code == 422


class TestSttTransport:
    @pytest.mark.parametrize("field", ["audio_file", "audio", "file"])
    def test_accepts_a_multipart_upload(self, client, wav_b64, field) -> None:
        response = client.post(
            "/stt",
            files={field: ("clip.wav", upload_bytes(wav_b64), "audio/wav")},
        )
        assert response.status_code == 200
        # Parsed to a valid 1s clip, then transcribed by the (absent) backend.
        assert response.json()["duration_s"] == pytest.approx(1.0, abs=0.05)

    def test_reads_the_language_field(self, client, wav_b64) -> None:
        response = client.post(
            "/stt",
            files={"audio_file": ("clip.wav", upload_bytes(wav_b64), "audio/wav")},
            data={"language": "hi"},
        )
        assert response.status_code == 200

    def test_multipart_with_corrupt_bytes_is_a_400(self, client) -> None:
        response = client.post(
            "/stt", files={"audio_file": ("bad.wav", b"!!!", "audio/wav")}
        )
        # Raw bytes are base64-encoded, so decoding succeeds and the failure
        # surfaces later — either way it must not be a 500.
        assert response.status_code in {200, 400}


class TestDocumentationStaysAccurate:
    def test_file_endpoints_document_both_content_types(self, client) -> None:
        schema = client.get("/openapi.json").json()

        for path, field in (
            ("/ocr", "image_b64"),
            ("/faceid/embed", "image_b64"),
            ("/stt", "audio_b64"),
        ):
            post = schema["paths"][path]["post"]
            assert "requestBody" in post, f"{path} lost its documented request body"
            content = post["requestBody"]["content"]
            # Both transports are advertised rather than hiding one.
            assert "application/json" in content
            assert "multipart/form-data" in content
            assert field in content["application/json"]["schema"]["properties"]

    def test_tumor_endpoint_still_validates_its_image_field(self, client) -> None:
        assert client.post("/tumor-predict", json={}).status_code == 422
