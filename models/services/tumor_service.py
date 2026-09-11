"""FB-05 — brain tumour classification from MRI.

Four classes: glioma, meningioma, pituitary, no_tumor. Architecture and class
order come from :mod:`architectures`, so training and serving cannot drift.

**No fallback, deliberately.** Every probability this endpoint returns is read by
a clinician. A hash-derived or uniform-random "prediction" would look exactly
like a real one on the wire. When the checkpoint is missing or torch is not
installed the correct answer is ``503 model_unavailable`` telling the operator to
run ``scripts/train_tumor.py`` — never a guess.

The response carries all four class probabilities, not just the argmax, because
"0.51 glioma / 0.49 meningioma" and "0.99 glioma" call for very different
clinical caution, and a single label hides that difference.
"""

from __future__ import annotations

from typing import Any

from architectures import CLASSES, DEFAULT_IMAGE_SIZE, build_tumor_model, tumor_transform
from catalog import model_id
from config import get_settings
from utils.confidence import normalize_confidence
from utils.errors import model_unavailable
from utils.heatmap import grad_cam_b64
from utils.images import decode_image, enforce_min_size, size_desc
from utils.loader import LazyModel

#: Filename the training script writes and the service reads.
WEIGHTS_FILENAME = "tumor_model.pth"


class TumorService:
    """Serves the 4-class MRI classifier, with optional Grad-CAM."""

    name = "tumor"
    endpoint = "/tumor-predict"

    def __init__(self) -> None:
        # No fallback: see the module docstring.
        self._model = LazyModel(
            "tumor",
            self._load_model,
            note="EfficientNet-B0 4-class MRI classifier; Grad-CAM capable",
        )
        self.models = (self._model,)

    # --- backend ----------------------------------------------------------
    @staticmethod
    def _load_model() -> dict[str, Any]:
        """Load the fine-tuned checkpoint. Raises so the endpoint can 503."""
        # Check the checkpoint first: it is the failure an operator can actually
        # fix, and a missing-weights message is more useful than an ImportError.
        weights_path = get_settings().weights_dir / WEIGHTS_FILENAME
        if not weights_path.exists():
            raise FileNotFoundError(
                f"tumour weights not found at {weights_path}; "
                "run `python scripts/download_data.py` then `python scripts/train_tumor.py`"
            )

        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "PyTorch is required for tumour inference: pip install torch torchvision "
                "--index-url https://download.pytorch.org/whl/cpu"
            ) from exc

        payload = torch.load(str(weights_path), map_location="cpu")
        state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
        classes = tuple(payload.get("classes", CLASSES)) if isinstance(payload, dict) else CLASSES
        image_size = int(payload.get("image_size", DEFAULT_IMAGE_SIZE)) if isinstance(payload, dict) else DEFAULT_IMAGE_SIZE

        model = build_tumor_model(num_classes=len(classes), pretrained=False)
        model.load_state_dict(state_dict)

        device = get_settings().device
        model.to(device)
        model.eval()
        return {
            "model": model,
            "device": device,
            "classes": classes,
            "image_size": image_size,
            "trained_at": payload.get("trained_at") if isinstance(payload, dict) else None,
            "val_accuracy": payload.get("val_accuracy") if isinstance(payload, dict) else None,
        }

    # --- introspection ----------------------------------------------------
    @property
    def available(self) -> bool:
        return self._model.available

    @property
    def serving_key(self) -> str:
        return "tumor"

    def model_version(self) -> str:
        return model_id("tumor")

    def warmup(self) -> dict[str, bool]:
        return {self._model.key: self._model.warm()}

    def _require_model(self) -> dict[str, Any]:
        try:
            bundle = self._model.load()
        except Exception as exc:  # noqa: BLE001 - surfaced as a typed 503
            raise model_unavailable(str(exc)) from exc
        if not self._model.available:
            raise model_unavailable(str(self._model.last_error))
        return bundle

    # --- inference --------------------------------------------------------
    def predict(self, image_b64: str, *, with_heatmap: bool = False) -> dict[str, Any]:
        """Classify one MRI slice and return all class probabilities."""
        image = decode_image(image_b64)
        enforce_min_size(image)
        input_size = size_desc(image)

        bundle = self._require_model()
        probabilities, class_index = self._forward(bundle, image)

        classes = bundle["classes"]
        named = {
            label: round(float(probability), 4)
            for label, probability in zip(classes, probabilities)
        }
        prediction = classes[class_index]

        heatmap = None
        if with_heatmap:
            heatmap = self._heatmap(bundle, image, class_index)

        return {
            "prediction": prediction,
            "confidence": normalize_confidence(probabilities[class_index]),
            "class_probabilities": named,
            "heatmap_b64": heatmap,
            "input_size": input_size,
            "classes": list(classes),
        }

    def _forward(self, bundle: dict[str, Any], image: Any) -> tuple[list[float], int]:
        """Preprocess, run the network and softmax the logits."""
        import torch

        transform = tumor_transform(bundle["image_size"], train=False)
        tensor = transform(image).unsqueeze(0).to(bundle["device"])

        with torch.no_grad():
            logits = bundle["model"](tensor)
            probabilities = torch.softmax(logits, dim=-1)[0].cpu().tolist()

        class_index = int(max(range(len(probabilities)), key=lambda i: probabilities[i]))
        return probabilities, class_index

    @staticmethod
    def _heatmap(bundle: dict[str, Any], image: Any, class_index: int) -> str | None:
        """Grad-CAM for the predicted class, on the last feature block."""
        import torch

        transform = tumor_transform(bundle["image_size"], train=False)
        tensor = transform(image).unsqueeze(0).to(bundle["device"])
        tensor.requires_grad_(True)

        target_layer = bundle["model"].features[-1]
        return grad_cam_b64(
            bundle["model"],
            tensor,
            image,
            target_layer=target_layer,
            class_index=class_index,
        )


SERVICE = TumorService()
