"""FB-08 — embeddings for the backend's RAG index.

Primary backend: ``sentence-transformers/all-MiniLM-L6-v2`` (384 dimensions).
Fallback: a deterministic signed-hashing embedder, also 384-dimensional.

The fallback is honest about what it is. Hashed n-grams preserve lexical overlap,
so exact and near-exact matches still retrieve sensibly and the RAG pipeline can
be built and tested end to end; but they capture no semantics, so
"heart attack" and "myocardial infarction" will not be close. Retrieval quality
with the fallback is therefore poor, and ``/health`` reports the model as
degraded rather than letting the backend believe it has real embeddings.

Batch cap: 100 texts per call, per the internal contract. Larger requests are
rejected with a clear error rather than silently truncated or chunked, so the
caller's batching logic cannot develop a silent off-by-one.
"""

from __future__ import annotations

import hashlib
from typing import Any

from catalog import model_id
from config import get_settings
from utils.errors import ModelServiceError
from utils.loader import LazyModel

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

#: Output dimensionality the backend's index is built around.
EMBEDDING_DIM = 384

#: Token n-gram sizes mixed by the hashing fallback.
NGRAM_SIZES: tuple[int, ...] = (1, 2)


def hashing_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Deterministic signed-hashing embedding, L2-normalised.

    Each token unigram and bigram is hashed to a bucket; one bit of the digest
    picks the sign. Normalising makes cosine similarity a plain dot product, the
    same contract the MiniLM backend satisfies. An empty string yields a zero
    vector.
    """
    import numpy as np

    vector = np.zeros(dim, dtype=np.float32)
    tokens = (text or "").lower().split()

    features: list[str] = list(tokens)
    for size in NGRAM_SIZES:
        if size <= 1:
            continue
        features.extend(
            " ".join(tokens[index : index + size])
            for index in range(max(0, len(tokens) - size + 1))
        )
    if not features:
        return [0.0] * dim

    # Collision-free per bucket by construction of the 64-bit digest.
    for feature in features:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        index = value % dim
        sign = 1.0 if (value >> 63) & 1 else -1.0
        vector[index] += sign

    norm = float(np.linalg.norm(vector))
    if norm == 0.0:
        return [0.0] * dim
    vector /= norm
    return [round(float(value), 6) for value in vector]


class EmbedService:
    """Turns text into L2-normalised vectors for retrieval."""

    name = "embed"
    endpoint = "/embed"

    def __init__(self) -> None:
        self._model = LazyModel(
            "minilm",
            self._load_minilm,
            fallback=self._load_hashing,
            fallback_key="hashing_embed",
            note="MiniLM sentence embeddings; lexical hashing serves when unavailable",
        )
        self.models = (self._model,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_minilm() -> dict[str, Any]:
        """Load MiniLM once onto the configured device."""
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(MODEL_NAME, device=get_settings().device)
        return {"engine": "sentence-transformers", "model": model, "dim": EMBEDDING_DIM}

    @staticmethod
    def _load_hashing() -> dict[str, Any]:
        """Fallback marker; encoding lives in :func:`hashing_embedding`."""
        return {"engine": "hashing", "dim": EMBEDDING_DIM}

    # --- introspection ----------------------------------------------------
    @property
    def engine(self) -> str:
        return "sentence-transformers" if self._model.available else "hashing"

    @property
    def serving_key(self) -> str:
        return "minilm" if self._model.available else "hashing_embed"

    @property
    def degraded(self) -> bool:
        return self._model.serving_fallback

    def dim(self) -> int:
        return int(self._model.load().get("dim", EMBEDDING_DIM))

    def model_version(self) -> str:
        return model_id(self.serving_key)

    def warmup(self) -> dict[str, bool]:
        return {self._model.key: self._model.warm()}

    # --- inference --------------------------------------------------------
    def embed(self, texts: list[str]) -> dict[str, Any]:
        """Embed a batch of texts, enforcing the per-call cap."""
        limit = get_settings().max_embed_batch
        if len(texts) > limit:
            raise ModelServiceError(
                "batch_too_large",
                f"{len(texts)} texts exceeds the {limit}-text cap per call",
                422,
            )

        bundle = self._model.load()
        vectors = self._encode(bundle, texts)

        return {
            "embeddings": vectors,
            "dim": int(bundle.get("dim", EMBEDDING_DIM)),
            "engine": str(bundle["engine"]),
            "degraded": self.degraded,
        }

    def _encode(self, bundle: dict[str, Any], texts: list[str]) -> list[list[float]]:
        """Dispatch to the serving backend; both return L2-normalised vectors."""
        if bundle["engine"] == "sentence-transformers":
            vectors = bundle["model"].encode(
                texts,
                normalize_embeddings=True,
                batch_size=32,
                show_progress_bar=False,
            )
            return [[round(float(value), 6) for value in vector] for vector in vectors]

        dim = int(bundle.get("dim", EMBEDDING_DIM))
        return [hashing_embedding(text, dim) for text in texts]


SERVICE = EmbedService()
