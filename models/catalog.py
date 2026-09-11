"""Single source of truth for model identity, versions and provenance.

FB-12 requires every model to carry a version tag, and the research paper needs a
reproducible record of exactly which weights produced a given prediction. Both
read from here, so there is exactly one place to bump a version.

``key``       short slug used in the registry, the SQLite log and reports.
``model_id``  human-facing versioned identifier surfaced by ``/health``.
``source``    HF repo id, weights filename, or "builtin" for hand-written logic.
``backend``   the runtime that serves it (torch / sklearn / xgboost / regex ...).
``heavy``     True when serving it needs an optional dependency from
              requirements-models.txt. Heavy models load lazily, never at import.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_id: str
    source: str
    backend: str
    heavy: bool
    description: str


#: Every model the service can serve, including pure-Python fallbacks.
CATALOG: dict[str, ModelSpec] = {
    # --- FB-02 dual OCR ---------------------------------------------------
    "donut": ModelSpec(
        key="donut",
        model_id="donut-v1.0",
        source="chinmays18/medical-prescription-ocr",
        backend="transformers",
        heavy=True,
        description="Donut fine-tune for per-field prescription extraction.",
    ),
    "chandra": ModelSpec(
        key="chandra",
        model_id="chandra-v1.0",
        source="datalab-to/chandra-ocr-2",
        backend="chandra",
        heavy=True,
        description="Chandra VLM; primary layout-preserving markdown output.",
    ),
    "ocr_merge": ModelSpec(
        key="ocr_merge",
        model_id="ocr-merge-v1.0",
        source="builtin",
        backend="python",
        heavy=False,
        description="Character-edit-distance merger of Donut + Chandra outputs.",
    ),
    # --- FB-03 clinical NER ----------------------------------------------
    "medspacy": ModelSpec(
        key="medspacy",
        model_id="medspacy-ner-v1.0",
        source="en_core_med7_lg|en_ner_bc5cdr_md",
        backend="spacy",
        heavy=True,
        description="medspaCy clinical NER: DRUG / DOSAGE / FREQUENCY / CONDITION.",
    ),
    "ner_regex": ModelSpec(
        key="ner_regex",
        model_id="ner-regex-v1.0",
        source="builtin",
        backend="regex",
        heavy=False,
        description="Dictionary + regex fallback extractor for prescription text.",
    ),
    # --- FB-04 face identification ---------------------------------------
    "uniface": ModelSpec(
        key="uniface",
        model_id="uniface-arcface-v1.0",
        source="yakhyo/uniface",
        backend="onnx",
        heavy=True,
        description="ArcFace embedding + liveness; embeddings only, never raw images.",
    ),
    # --- FB-05 brain tumour ----------------------------------------------
    "tumor": ModelSpec(
        key="tumor",
        model_id="tumor-v1.0",
        source="weights/tumor_model.pth",
        backend="torch",
        heavy=True,
        description="EfficientNet-B0 4-class MRI classifier (Grad-CAM capable).",
    ),
    # --- FB-06 symptom checker -------------------------------------------
    "symptoms": ModelSpec(
        key="symptoms",
        model_id="symptoms-sk-v1.0",
        source="weights/symptom_model.pkl",
        backend="sklearn",
        heavy=True,
        description="Multi-hot symptom classifier over a public disease dataset.",
    ),
    "symptoms_rules": ModelSpec(
        key="symptoms_rules",
        model_id="symptoms-rules-v1.0",
        source="builtin",
        backend="rules",
        heavy=False,
        description="Keyword rules engine with a curated condition knowledge base.",
    ),
    # --- FB-07 sepsis -----------------------------------------------------
    "sepsis": ModelSpec(
        key="sepsis",
        model_id="sepsis-xgb-v1.0",
        source="weights/sepsis_model.pkl",
        backend="xgboost",
        heavy=True,
        description="XGBoost sepsis-onset classifier with TreeSHAP explanations.",
    ),
    "sepsis_heuristic": ModelSpec(
        key="sepsis_heuristic",
        model_id="sepsis-qsofa-v1.0",
        source="builtin",
        backend="rules",
        heavy=False,
        description="Transparent qSOFA/SOFA-inspired logistic fallback scoring.",
    ),
    # --- FB-08 embeddings -------------------------------------------------
    "minilm": ModelSpec(
        key="minilm",
        model_id="minilm-l6-v1.0",
        source="sentence-transformers/all-MiniLM-L6-v2",
        backend="sentence-transformers",
        heavy=True,
        description="384-dim sentence embeddings for the backend's RAG index.",
    ),
    "hashing_embed": ModelSpec(
        key="hashing_embed",
        model_id="hashing-embed-v1.0",
        source="builtin",
        backend="numpy",
        heavy=False,
        description="Deterministic 384-dim hashing embedder for degraded mode.",
    ),
    # --- FB-09 / FB-10 speech --------------------------------------------
    "whisper": ModelSpec(
        key="whisper",
        model_id="whisper-base-v1.0",
        source="openai/whisper-base",
        backend="faster-whisper|transformers",
        heavy=True,
        description="Speech-to-text with automatic language detection.",
    ),
    "coqui_tts": ModelSpec(
        key="coqui_tts",
        model_id="tts-tacotron2-v1.0",
        source="tts_models/en/ljspeech/tacotron2-DDC",
        backend="coqui",
        heavy=True,
        description="Neural text-to-speech.",
    ),
    "gtts": ModelSpec(
        key="gtts",
        model_id="tts-gtts-v1.0",
        source="gTTS",
        backend="gtts",
        heavy=True,
        description="Online TTS fallback; needs network access.",
    ),
    "tts_silent": ModelSpec(
        key="tts_silent",
        model_id="tts-silent-v1.0",
        source="builtin",
        backend="wave",
        heavy=False,
        description="Silent WAV placeholder so callers get a valid audio container.",
    ),
}


def spec(key: str) -> ModelSpec:
    """Look up a model spec, failing loudly on typos during development."""
    try:
        return CATALOG[key]
    except KeyError as exc:  # pragma: no cover - programmer error
        raise KeyError(f"unknown model key {key!r}") from exc


def model_id(key: str) -> str:
    """Versioned identifier for ``key``, used in responses and the log."""
    return spec(key).model_id
