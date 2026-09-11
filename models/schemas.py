"""Request and response schemas for the internal model service (port 9000).

These mirror the endpoints in the FreeBuff brief. Two extra fields appear on
every response beyond the agreed shape, because rule 5 requires them for the
research paper's evaluation:

* ``model_version``      which weights produced this answer;
* ``inference_time_ms``  how long they took.

A third field, ``degraded``, is added wherever a fallback can serve in place of
the real model. It is ``True`` only when the answer did **not** come from the
real model, so a caller can always tell them apart.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high"]


class TimedResponse(BaseModel):
    """Fields every endpoint returns, per rule 5 of the brief."""

    inference_time_ms: float = Field(..., ge=0.0)
    model_version: str


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

class ImageRequest(BaseModel):
    image_b64: str = Field(..., min_length=1, description="Base64 image bytes")


class TextRequest(BaseModel):
    text: str = Field(..., description="Raw text to analyse")


class EmbedRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1)


class SymptomsRequest(BaseModel):
    symptoms: list[str] = Field(..., min_length=1)


class Vitals(BaseModel):
    """Five SOFA-inspired vitals. Units are the ones the backend collects."""

    temp: float = Field(..., description="Body temperature in Celsius")
    hr: float = Field(..., description="Heart rate, beats per minute")
    rr: float = Field(..., description="Respiratory rate, breaths per minute")
    wbc: float = Field(..., description="White cell count, 10^3/uL")
    lactate: float = Field(..., description="Serum lactate, mmol/L")


class SepsisRequest(BaseModel):
    vitals: Vitals


class SttRequest(BaseModel):
    audio_b64: str = Field(..., min_length=1)
    language: str | None = Field(default=None, description="ISO code; omit to auto-detect")


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    language: str | None = Field(default=None, description="ISO code, e.g. 'en' or 'hi'")


# --------------------------------------------------------------------------
# OCR (FB-02)
# --------------------------------------------------------------------------

class DonutOutput(BaseModel):
    text: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class ChandraOutput(BaseModel):
    text: str = ""
    markdown: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class StructuredPrescription(BaseModel):
    drugs: list[str] = Field(default_factory=list)
    diagnosis: str = ""
    date: str = ""


class MergedOutput(BaseModel):
    structured: StructuredPrescription
    text: str = ""
    engine: str = "regex"
    drug_agreement: float = Field(0.0, ge=0.0, le=1.0)


class OcrResponse(TimedResponse):
    donut: DonutOutput
    chandra: ChandraOutput
    merged: MergedOutput
    agreement: float = Field(
        ..., ge=0.0, le=1.0,
        description="1 - CER between the two engines' text outputs",
    )
    engines: dict[str, str] = Field(
        default_factory=dict,
        description="engine -> serving version, or 'unavailable'",
    )
    timings: dict[str, float] = Field(
        default_factory=dict,
        description="Per-engine latency in milliseconds, for the paper's tables",
    )
    degraded: bool = False


# --------------------------------------------------------------------------
# NER (FB-03)
# --------------------------------------------------------------------------

class NerResponse(TimedResponse):
    drugs: list[str] = Field(default_factory=list)
    dosages: list[str] = Field(default_factory=list)
    frequencies: list[str] = Field(default_factory=list)
    diagnosis: str = ""
    engine: str = "regex"
    degraded: bool = False
    confidence: float = Field(0.0, ge=0.0, le=1.0)


# --------------------------------------------------------------------------
# Tumour classification (FB-05)
# --------------------------------------------------------------------------

TumorClass = Literal["glioma", "meningioma", "pituitary", "no_tumor", "unavailable"]


class TumorResponse(TimedResponse):
    prediction: TumorClass
    confidence: float = Field(..., ge=0.0, le=1.0)
    class_probabilities: dict[str, float]
    heatmap_b64: str | None = None
    degraded: bool = False
    note: str | None = None


# --------------------------------------------------------------------------
# Symptom checker (FB-06)
# --------------------------------------------------------------------------

class ConditionScore(BaseModel):
    condition: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class SymptomsResponse(TimedResponse):
    conditions: list[str] = Field(default_factory=list)
    condition_scores: list[ConditionScore] = Field(default_factory=list)
    severity: Severity
    see_doctor: bool
    engine: str = "rules"
    degraded: bool = False
    disclaimer: str = (
        "Symptom triage is decision support only and is not a diagnosis."
    )


# --------------------------------------------------------------------------
# Sepsis risk (FB-07)
# --------------------------------------------------------------------------

class ShapValue(BaseModel):
    feature: str
    value: float
    impact: float = Field(..., description="Signed contribution to the risk score")


class SepsisResponse(TimedResponse):
    risk_score: float = Field(..., ge=0.0, le=100.0)
    risk_level: Severity
    shap_values: list[ShapValue] = Field(default_factory=list)
    explanation: str = ""
    explanation_method: Literal["shap", "linear-contribution"] = Field(
        default="shap",
        description=(
            "'shap' for TreeSHAP attributions; 'linear-contribution' when the "
            "transparent logistic fallback served instead"
        ),
    )
    engine: str = "xgboost"
    degraded: bool = False


# --------------------------------------------------------------------------
# Embeddings (FB-08)
# --------------------------------------------------------------------------

class EmbedResponse(BaseModel):
    embeddings: list[list[float]]
    model: str
    dim: int
    inference_time_ms: float = Field(..., ge=0.0)
    degraded: bool = False


# --------------------------------------------------------------------------
# Speech (FB-09, FB-10)
# --------------------------------------------------------------------------

class SttResponse(TimedResponse):
    transcript: str = ""
    language_detected: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    duration_s: float = Field(0.0, ge=0.0)
    degraded: bool = False
    note: str | None = None


class TtsResponse(TimedResponse):
    audio_b64: str
    duration_s: float = Field(..., ge=0.0)
    engine: str = Field(
        default="coqui",
        description="'coqui' (WAV), 'gtts' (MP3), or 'silent' (placeholder WAV)",
    )
    audio_format: Literal["wav", "mp3"] = Field(
        default="wav",
        description="Container of the returned audio; gTTS can only produce MP3",
    )
    degraded: bool = False
    note: str | None = None


# --------------------------------------------------------------------------
# Face identification (FB-04)
# --------------------------------------------------------------------------

class FaceEmbedResponse(TimedResponse):
    embedding: list[float]
    dim: int
    liveness_score: float = Field(..., ge=0.0, le=1.0)
    liveness_passed: bool
    liveness_method: str = Field(
        default="texture-heuristic",
        description="Which liveness check ran; a heuristic, not a certified PAD model",
    )


# --------------------------------------------------------------------------
# Health (FB-01, FB-12)
# --------------------------------------------------------------------------

class ModelHealth(BaseModel):
    key: str
    model_id: str
    backend: str
    source: str
    heavy: bool
    status: str
    loaded_at: str | None = None
    load_ms: float | None = None
    reason: str | None = None
    serving: bool
    degraded: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    models_loaded: list[str] = Field(
        default_factory=list,
        description="Keys currently serving, including fallbacks",
    )
    models: list[ModelHealth] = Field(default_factory=list)
    gpu: bool
    device: str
    service_version: str
    degraded_models: list[str] = Field(default_factory=list)
