"""FB-04 — face enrolment embeddings.

Extracts one ArcFace embedding from one detected face, plus a liveness score.
Only the embedding ever leaves this service; no image is stored or returned
(``/faceid/enroll`` on the backend persists the vector, not the photo).

**This service has no fallback, by design.** Every other model here degrades to
a labelled fallback rather than failing. Identity does not: a hash-derived or
random embedding would produce confident *wrong* patient matches, and a wrong
patient in a clinical record is worse than an error. So when UniFace is not
installed, ``/faceid/embed`` returns ``503 model_unavailable``.

**Liveness.** UniFace ships detection and recognition, not presentation-attack
detection, so liveness is a documented heuristic: facial texture energy
(Laplacian variance) discounted by the fraction of blown-out highlights typical
of a re-photographed screen. It rejects blank frames, flat prints and phone
screens pointed at the camera. It is **not** a certified PAD model and should be
replaced by one (e.g. MiniFASNet) before any production use; the response says
so via ``liveness_method``.
"""

from __future__ import annotations

from typing import Any

from catalog import model_id
from config import get_settings
from utils.confidence import normalize_confidence
from utils.errors import model_unavailable, no_face_detected
from utils.images import decode_image, enforce_min_size, size_desc
from utils.loader import LazyModel

#: Var software the Laplacian variance is squashed by. Lower = stricter.
TEXTURE_SCALE = 200.0

#: Pixels at or above this value count as blown-out highlight.
HIGHLIGHT_LEVEL = 250


class FaceIdService:
    """ArcFace embedding extraction with a single-face requirement."""

    name = "faceid"
    endpoint = "/faceid/embed"

    def __init__(self) -> None:
        # No fallback: identity must not be guessed.
        self._app = LazyModel(
            "uniface",
            self._load_uniface,
            note="ArcFace embeddings only; no raw images are stored or returned",
        )
        self.models = (self._app,)

    # --- backend ----------------------------------------------------------
    @staticmethod
    def _load_uniface() -> Any:
        """Load UniFace's analyser once, on CPU."""
        from uniface import FaceAnalysis

        app = FaceAnalysis(providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=0, det_size=(640, 640))
        return app

    # --- introspection ----------------------------------------------------
    @property
    def available(self) -> bool:
        return self._app.available

    @property
    def serving_key(self) -> str:
        return "uniface"

    def model_version(self) -> str:
        return model_id("uniface")

    def warmup(self) -> dict[str, bool]:
        return {self._app.key: self._app.warm()}

    def _require_app(self) -> Any:
        """Resolve the analyser or refuse — never substitute a placeholder."""
        try:
            app = self._app.load()
        except Exception as exc:  # noqa: BLE001 - surfaced as a typed 503
            raise model_unavailable(
                "face recognition backend unavailable; install uniface "
                f"(cause: {type(exc).__name__}: {exc})"
            ) from exc
        if not self._app.available:
            raise model_unavailable(
                f"face recognition backend unavailable ({self._app.last_error}); "
                "install uniface to enable /faceid/embed"
            )
        return app

    # --- inference --------------------------------------------------------
    def embed(self, image_b64: str) -> dict[str, Any]:
        """Detect exactly one face and return its embedding and liveness score."""
        # Input validation first: a malformed request is the caller's fault and
        # should be a 400 even when the backend happens to be unavailable.
        image = decode_image(image_b64)
        enforce_min_size(image)
        input_size = size_desc(image)

        app = self._require_app()
        faces = self._detect(app, image)
        if len(faces) != 1:
            # 0 faces: nothing to enrol. >1: ambiguous, and picking one would be
            # a silent guess about who is enrolling.
            raise no_face_detected(
                f"expected exactly one face, found {len(faces)}"
            )

        embedding = self._embedding_of(faces[0])
        liveness_score = self.liveness_score(image)
        threshold = get_settings().liveness_threshold

        return {
            "embedding": embedding,
            "dim": len(embedding),
            "liveness_score": liveness_score,
            "liveness_passed": liveness_score >= threshold,
            "liveness_method": "texture-heuristic",
            "input_size": input_size,
        }

    @staticmethod
    def _detect(app: Any, image: Any) -> list[Any]:
        """Run face detection on a BGR view of the image."""
        import numpy as np

        rgb = np.asarray(image, dtype=np.uint8)
        bgr = rgb[:, :, ::-1]  # insightface-family models expect BGR
        faces = app.get(bgr)
        return list(faces) if faces is not None else []

    @staticmethod
    def _embedding_of(face: Any) -> list[float]:
        """L2-normalised ArcFace embedding, so cosine similarity is a dot product."""
        import numpy as np

        vector = getattr(face, "normed_embedding", None)
        if vector is None:
            vector = getattr(face, "embedding", None)
        if vector is None:
            raise model_unavailable("face detected but no embedding was produced")

        array = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(array))
        if norm == 0.0:
            raise model_unavailable("face embedding was degenerate (zero norm)")
        return [round(float(value), 6) for value in (array / norm)]

    @staticmethod
    def liveness_score(image: Any) -> float:
        """Texture-energy liveness heuristic. See the module docstring.

        Returns a score in ``[0, 1]``: high for a textured, well-exposed face,
        low for a blank frame, a flat print, or a screen with blown highlights.
        """
        import numpy as np
        from scipy import ndimage

        grey = np.asarray(image.convert("L"), dtype=np.float32)

        texture = float(ndimage.laplace(grey).var())
        texture_term = texture / (texture + TEXTURE_SCALE) if texture > 0.0 else 0.0

        total = float(grey.size) or 1.0
        highlight_ratio = float((grey >= HIGHLIGHT_LEVEL).sum()) / total
        highlight_term = max(0.0, 1.0 - 4.0 * highlight_ratio)

        return normalize_confidence(texture_term * highlight_term)


SERVICE = FaceIdService()
