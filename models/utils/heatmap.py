"""Grad-CAM heatmap generation.

The brief marks Grad-CAM as optional for the MVP and required for the polish
phase. It is implemented here because a tumour classifier that shows *where* it
looked is far more useful to a clinician than one that only prints a label, and
because the paper needs a figure.

Implemented directly rather than via the ``grad-cam`` package: the algorithm is
about thirty lines, and this avoids another optional dependency that could fail
on a GPU-less box.
"""

from __future__ import annotations

from typing import Any

#: Warm colormap stops. It starts at pure black on purpose: zero activation
#: then means "the model looked nowhere here" and leaves the underlying image
#: untouched, instead of tinting every pixel blue the way the classic jet
#: colormap does. Only regions the model actually used get coloured.
_COLORMAP_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.0, (0, 0, 0)),
    (0.25, (130, 0, 0)),
    (0.5, (225, 50, 0)),
    (0.75, (255, 180, 0)),
    (1.0, (255, 255, 220)),
)


def _apply_colormap(cam: Any) -> Any:
    """Map a normalised ``[0, 1]`` map to RGB using linear interpolation."""
    import numpy as np

    stops = np.array([stop for stop, _ in _COLORMAP_STOPS], dtype=np.float32)
    colours = np.array([colour for _, colour in _COLORMAP_STOPS], dtype=np.float32)

    flat = cam.reshape(-1)
    channels = [
        np.interp(flat, stops, colours[:, channel]).astype(np.uint8)
        for channel in range(3)
    ]
    return np.stack(channels, axis=-1).reshape(cam.shape + (3,))


def normalise_map(cam: Any) -> Any:
    """Scale a raw CAM to ``[0, 1]``; all-zero maps stay all-zero."""
    import numpy as np

    array = np.asarray(cam, dtype=np.float32)
    lowest, highest = float(array.min()), float(array.max())
    if highest - lowest < 1e-8:
        return np.zeros_like(array)
    return (array - lowest) / (highest - lowest)


def overlay_heatmap(image: Any, cam: Any, *, alpha: float = 0.45, resize_to_image: bool = True) -> Any:
    """Blend a heatmap over ``image``, returning a new RGB PIL image.

    The blend strength is *spatially weighted* by the map itself: regions the
    model ignored come through unchanged, and only attended regions are tinted.
    A uniform blend would darken the whole scan even where the model had no
    opinion, which reads as if those pixels mattered.
    """
    import numpy as np
    from PIL import Image

    base = image.convert("RGB")
    normalised = normalise_map(cam)

    if resize_to_image:
        # Bilinear upsampling matches what the eye expects from a CAM overlay.
        heat = Image.fromarray((normalised * 255).astype(np.uint8)).resize(
            base.size, resample=Image.BILINEAR
        )
        normalised = np.asarray(heat, dtype=np.float32) / 255.0

    coloured = _apply_colormap(normalised)
    weight = (normalised * alpha)[..., None]
    blended = np.asarray(base, dtype=np.float32) * (1.0 - weight) + coloured * weight
    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))


def grad_cam(
    model: Any,
    input_tensor: Any,
    *,
    target_layer: Any,
    class_index: int,
) -> Any:
    """Compute a Grad-CAM map for ``class_index``.

    Gradients are taken with respect to the target layer's activations, averaged
    across channels to give per-channel weights, and used to weight those same
    activations. ReLU keeps the evidence that supports the class.
    """
    import numpy as np
    import torch

    activations: dict[str, Any] = {}
    gradients: dict[str, Any] = {}

    def forward_hook(_module: Any, _inputs: Any, output: Any) -> None:
        activations["value"] = output.detach()

    def backward_hook(_module: Any, _grad_input: Any, grad_output: Any) -> None:
        gradients["value"] = grad_output[0].detach()

    handles = [
        target_layer.register_forward_hook(forward_hook),
        target_layer.register_full_backward_hook(backward_hook),
    ]
    try:
        model.zero_grad(set_to_none=True)
        outputs = model(input_tensor)
        score = outputs[0, class_index]
        score.backward()

        if "value" not in activations or "value" not in gradients:
            raise RuntimeError("Grad-CAM hooks did not fire; wrong target layer?")

        activation = activations["value"][0]
        gradient = gradients["value"][0]
        weights = gradient.mean(dim=(1, 2), keepdim=True)
        cam = torch.relu((weights * activation).sum(dim=0))
        return cam.cpu().numpy().astype(np.float32)
    finally:
        for handle in handles:
            handle.remove()


def grad_cam_b64(
    model: Any,
    input_tensor: Any,
    image: Any,
    *,
    target_layer: Any,
    class_index: int,
    alpha: float = 0.45,
) -> str | None:
    """Full pipeline: CAM -> colourmap overlay -> base64 PNG. ``None`` on failure.

    Heatmaps are a nicety; a failure to produce one must never fail the
    prediction it would have illustrated.
    """
    from utils.images import pil_to_b64_png

    try:
        cam = grad_cam(model, input_tensor, target_layer=target_layer, class_index=class_index)
        overlay = overlay_heatmap(image, cam, alpha=alpha)
        return pil_to_b64_png(overlay)
    except Exception:  # noqa: BLE001
        return None
