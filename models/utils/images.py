"""Image decoding and encoding helpers.

The internal API carries images as base64 strings over JSON, so every imaging
endpoint funnels through here. Decoding failures become ``invalid_image`` rather
than a 500, and a size guard rejects images too small to be a real scan before
they reach a model.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
from typing import Any

from config import get_settings
from utils.errors import bad_image

MAX_IMAGE_BYTES = 25 * 1024 * 1024  # 25 MB decoded; a phone photo is well under.


def strip_data_uri(payload: str) -> str:
    """Drop a ``data:image/png;base64,`` prefix if the client sent one."""
    if not isinstance(payload, str):
        raise bad_image("image payload must be a base64 string")
    if payload.startswith("data:") and "," in payload:
        return payload.split(",", 1)[1]
    return payload


def decode_b64_image(image_b64: str) -> bytes:
    """Decode a base64 image into raw bytes, normalising common client quirks."""
    cleaned = "".join(strip_data_uri(image_b64).split())
    if not cleaned:
        raise bad_image("empty image payload")
    # Clients that stripped padding are common; restore it rather than failing.
    padding = (-len(cleaned)) % 4
    try:
        data = base64.b64decode(cleaned + "=" * padding, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise bad_image(f"base64 decode failed: {exc}") from exc
    if not data:
        raise bad_image("decoded image is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise bad_image(f"image too large ({len(data)} bytes)")
    return data


def load_pil(data: bytes, *, convert: str | None = "RGB") -> Any:
    """Decode bytes into a PIL image, optionally converting colour space."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - pillow is a core dependency
        raise bad_image("image support unavailable: pillow is not installed") from exc

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:  # noqa: BLE001 - PIL raises many types
        raise bad_image(f"unsupported or corrupt image: {exc}") from exc
    if convert:
        image = image.convert(convert)
    return image


def decode_image(image_b64: str) -> Any:
    """base64 string -> validated PIL image in RGB."""
    return load_pil(decode_b64_image(image_b64))


def to_numpy_rgb(image_b64: str) -> Any:
    """base64 string -> ``(H, W, 3)`` uint8 numpy array."""
    import numpy as np

    image = decode_image(image_b64)
    return np.asarray(image, dtype=np.uint8)


def enforce_min_size(image: Any) -> None:
    """Reject images too small for the downstream model to say anything useful."""
    minimum = get_settings().min_image_side
    width, height = image.size
    if min(width, height) < minimum:
        raise bad_image(
            f"image too small: {width}x{height}, minimum side is {minimum}px"
        )


def size_desc(image: Any) -> str:
    """``"WxH"`` descriptor recorded with every logged inference."""
    width, height = image.size
    return f"{width}x{height}"


def image_desc(image_b64: str) -> str:
    """Best-effort size descriptor; never raises (logging must not fail requests)."""
    try:
        return size_desc(decode_image(image_b64))
    except Exception:  # noqa: BLE001
        return "unknown"


def pil_to_b64_png(image: Any) -> str:
    """Encode a PIL image (e.g. a heatmap) as a base64 PNG string."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def content_seed(data: bytes) -> int:
    """Stable integer derived from image bytes.

    Used only by explicitly-degraded backends so their placeholder output is at
    least deterministic across calls, which keeps tests and demos repeatable.
    """
    return int.from_bytes(hashlib.sha256(data).digest()[:8], "big")
