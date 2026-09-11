"""FB-05 tests — the ``/tumor-predict`` contract and the heatmap utilities.

The classifier needs torch plus a trained checkpoint, so the endpoint's hard-fail
contract and the pure heatmap maths are what get tested here. Those two are the
parts most likely to regress.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from architectures import CLASSES
from utils.heatmap import normalise_map, overlay_heatmap


class TestClassVocabulary:
    def test_four_classes_in_a_fixed_order(self) -> None:
        # Checkpoints store this order; changing it silently breaks them.
        assert CLASSES == ("glioma", "meningioma", "pituitary", "no_tumor")


class TestNormaliseMap:
    def test_scales_into_the_unit_interval(self) -> None:
        cam = np.array([[0.0, 5.0], [10.0, 20.0]], dtype=np.float32)
        normalised = normalise_map(cam)
        assert normalised.min() == 0.0
        assert normalised.max() == 1.0

    def test_a_constant_map_stays_zero_rather_than_dividing_by_zero(self) -> None:
        normalised = normalise_map(np.full((4, 4), 7.0, dtype=np.float32))
        assert np.all(normalised == 0.0)


class TestOverlayHeatmap:
    def test_returns_an_rgb_image_of_the_original_size(self) -> None:
        image = Image.new("RGB", (64, 48), "black")
        cam = np.zeros((7, 7), dtype=np.float32)
        cam[3, 3] = 1.0

        overlay = overlay_heatmap(image, cam)
        assert overlay.size == (64, 48)
        assert overlay.mode == "RGB"

    def test_a_zero_map_leaves_the_image_untouched(self) -> None:
        """Zero activation means the model looked nowhere, so nothing is tinted."""
        image = Image.new("RGB", (32, 32), (10, 20, 30))
        overlay = overlay_heatmap(image, np.zeros((4, 4), dtype=np.float32))
        assert np.array_equal(np.asarray(overlay), np.asarray(image))

    def test_only_the_hot_region_is_tinted(self) -> None:
        image = Image.new("RGB", (32, 32), (0, 0, 0))
        cam = np.zeros((8, 8), dtype=np.float32)
        cam[:2, :2] = 1.0  # top-left quadrant is the only evidence

        overlay = np.asarray(overlay_heatmap(image, cam))
        assert overlay[2, 2].sum() > 0      # inside the hot quadrant
        assert overlay[30, 30].sum() == 0   # outside it stays black

    def test_alpha_controls_blend_strength(self) -> None:
        image = Image.new("RGB", (32, 32), (0, 0, 0))
        cam = np.zeros((8, 8), dtype=np.float32)
        cam[:2, :2] = 1.0

        light = int(np.asarray(overlay_heatmap(image, cam, alpha=0.2))[2, 2].sum())
        heavy = int(np.asarray(overlay_heatmap(image, cam, alpha=0.8))[2, 2].sum())
        assert heavy > light > 0


class TestGradCamFailureIsContained:
    def test_returns_none_instead_of_raising(self) -> None:
        """A heatmap is a nicety; losing it must never lose the prediction."""
        from utils.heatmap import grad_cam_b64

        result = grad_cam_b64(
            object(),  # not a torch module
            object(),
            Image.new("RGB", (16, 16), "black"),
            target_layer=object(),
            class_index=0,
        )
        assert result is None


class TestTumorEndpoint:
    def test_reports_unavailable_rather_than_guessing_a_class(
        self, client, png_b64
    ) -> None:
        """A fabricated tumour prediction is worse than an error, so: 503."""
        response = client.post("/tumor-predict", json={"image_b64": png_b64})
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "model_unavailable"
        assert "tumor_model.pth" in body["message"]
        assert "train_tumor.py" in body["message"]

    def test_rejects_a_non_image_payload(self, client) -> None:
        response = client.post("/tumor-predict", json={"image_b64": "bm90IGFuIGltYWdl"})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"

    def test_rejects_an_image_too_small_to_classify(self, client, image_factory) -> None:
        response = client.post("/tumor-predict", json={"image_b64": image_factory(16, 16)})
        assert response.status_code == 400

    def test_missing_image_field_is_rejected(self, client) -> None:
        assert client.post("/tumor-predict", json={}).status_code == 422

    def test_heatmap_flag_is_accepted_and_defaults_to_off(self, client, png_b64) -> None:
        # Both forms must reach the model; neither is a 422.
        assert client.post("/tumor-predict", json={"image_b64": png_b64}).status_code == 503
        assert (
            client.post(
                "/tumor-predict", json={"image_b64": png_b64, "with_heatmap": True}
            ).status_code
            == 503
        )


@pytest.mark.heavy
class TestRealClassifier:
    def test_returns_four_probabilities_summing_to_one(self, client, png_b64) -> None:
        from services.tumor_service import SERVICE

        if not SERVICE._model.warm():
            pytest.skip("torch and/or tumour_model.pth are not available")

        body = client.post("/tumor-predict", json={"image_b64": png_b64}).json()
        assert set(body["class_probabilities"]) == set(CLASSES)
        assert abs(sum(body["class_probabilities"].values()) - 1.0) < 0.01
        assert body["prediction"] in CLASSES
