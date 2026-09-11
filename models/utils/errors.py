"""Typed service errors that map onto stable HTTP responses.

The public API contract spells out error payloads such as
``{error: "no_face_detected"}``. Raising :class:`ModelServiceError` keeps that
shape consistent instead of leaking FastAPI's default ``{"detail": ...}``.
"""

from __future__ import annotations


class ModelServiceError(Exception):
    """An error with a machine-readable code and an HTTP status."""

    def __init__(self, code: str, message: str = "", status_code: int = 400) -> None:
        self.code = code
        self.message = message or code
        self.status_code = status_code
        super().__init__(self.message)

    def as_dict(self) -> dict[str, str]:
        return {"error": self.code, "message": self.message}


def bad_image(detail: str = "image could not be decoded") -> ModelServiceError:
    return ModelServiceError("invalid_image", detail, 400)


def bad_audio(detail: str = "audio could not be decoded") -> ModelServiceError:
    return ModelServiceError("invalid_audio", detail, 400)


def no_face_detected(detail: str = "no face, or more than one face, detected") -> ModelServiceError:
    """FB-04: exactly one face is required to enrol or identify."""
    return ModelServiceError("no_face_detected", detail, 422)


def model_unavailable(detail: str) -> ModelServiceError:
    """Raised where a *fabricated* answer would be unsafe.

    Identity verification and tumour classification refuse to guess: returning a
    plausible-looking wrong answer is worse than returning an error. Endpoints
    that can degrade meaningfully (NER, triage rules, embeddings) never raise
    this — they return a labelled fallback instead.
    """
    return ModelServiceError("model_unavailable", detail, 503)
