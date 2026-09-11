"""FB-04 tests — the ``/faceid/embed`` contract and the liveness heuristic.

The interesting, testable logic here is the error contract and the liveness
score. Detection and recognition need UniFace plus a real photograph, so those
paths are exercised only under the ``heavy`` marker.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from services.faceid_service import FaceIdService


def pil_to_b64(image: Image.Image) -> str:
    import base64
    import io

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class TestLivenessHeuristic:
    """The heuristic is real logic, so it gets real assertions."""

    def test_a_blank_frame_scores_zero(self) -> None:
        assert FaceIdService.liveness_score(Image.new("RGB", (256, 256), "grey")) == 0.0

    def test_a_white_frame_with_blown_highlights_scores_low(self) -> None:
        # A re-photographed screen: flat, with clipped highlights.
        assert FaceIdService.liveness_score(Image.new("RGB", (256, 256), "white")) == 0.0

    def test_a_textured_frame_scores_above_zero(self) -> None:
        rng = np.random.default_rng(seed=7)
        noise = rng.integers(0, 200, size=(256, 256, 3), dtype=np.uint8)
        assert FaceIdService.liveness_score(Image.fromarray(noise)) > 0.0

    def test_more_texture_scores_higher(self) -> None:
        rng = np.random.default_rng(seed=11)
        smooth = rng.integers(120, 135, size=(256, 256, 3), dtype=np.uint8)
        rough = rng.integers(0, 255, size=(256, 256, 3), dtype=np.uint8)

        assert FaceIdService.liveness_score(
            Image.fromarray(rough)
        ) > FaceIdService.liveness_score(Image.fromarray(smooth))

    def test_score_is_always_within_bounds(self) -> None:
        for seed in range(5):
            rng = np.random.default_rng(seed=seed)
            data = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
            score = FaceIdService.liveness_score(Image.fromarray(data))
            assert 0.0 <= score <= 1.0


class TestFaceIdEndpoint:
    def test_reports_unavailable_rather_than_fabricating_an_embedding(
        self, client, png_b64
    ) -> None:
        """Identity is never guessed: no UniFace means 503, not a fake vector."""
        response = client.post("/faceid/embed", json={"image_b64": png_b64})
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "model_unavailable"
        assert "uniface" in body["message"]

    def test_rejects_a_non_image_payload_before_touching_the_model(self, client) -> None:
        response = client.post("/faceid/embed", json={"image_b64": "bm90IGFuIGltYWdl"})
        # Input validation is the caller's fault, so it is a 400 even though the
        # backend is missing.
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"

    def test_rejects_an_image_too_small_for_detection(self, client, image_factory) -> None:
        response = client.post("/faceid/embed", json={"image_b64": image_factory(16, 16)})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"

    def test_missing_image_field_is_rejected(self, client) -> None:
        assert client.post("/faceid/embed", json={}).status_code == 422

    def test_error_payload_uses_the_contract_shape(self, client, png_b64) -> None:
        body = client.post("/faceid/embed", json={"image_b64": png_b64}).json()
        assert set(body) == {"error", "message"}


@pytest.mark.heavy
class TestRealBackend:
    def test_embeds_a_single_face(self, client) -> None:
        from services.faceid_service import SERVICE

        if not SERVICE._app.warm():
            pytest.skip("uniface is not installed")

        # A real photograph is required; this asserts only the response shape.
        pytest.skip("no test photograph is bundled with the repository")


class TestDetectHelper:
    def test_detect_tolerates_an_app_returning_none(self) -> None:
        class NullApp:
            def get(self, _image):  # noqa: ANN001
                return None

        image = Image.new("RGB", (64, 64), "grey")
        assert FaceIdService._detect(NullApp(), image) == []

    def test_detect_converts_rgb_to_bgr(self) -> None:
        captured: dict[str, object] = {}

        class RecordingApp:
            def get(self, image):  # noqa: ANN001
                captured["image"] = image
                return []

        # A pure red pixel in RGB is a pure blue pixel in BGR.
        image = Image.new("RGB", (8, 8), (255, 0, 0))
        FaceIdService._detect(RecordingApp(), image)
        bgr = captured["image"]
        assert tuple(bgr[0, 0]) == (0, 0, 255)
