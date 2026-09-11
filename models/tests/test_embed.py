"""FB-08 tests — the ``/embed`` contract and the hashing fallback.

The hashing embedder is the backend that actually serves on a fresh clone, and
the RAG index is built on top of it, so its properties (determinism, unit norm,
lexical sensitivity) are asserted rather than assumed.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.embed_service import EMBEDDING_DIM, hashing_embedding


def cosine(left: list[float], right: list[float]) -> float:
    a, b = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else 0.0


class TestHashingEmbedding:
    def test_produces_the_declared_dimensionality(self) -> None:
        assert len(hashing_embedding("metformin 500 mg")) == EMBEDDING_DIM
        assert len(hashing_embedding("metformin", dim=128)) == 128

    def test_vectors_are_unit_norm(self) -> None:
        vector = hashing_embedding("atorvastatin 10 mg once daily")
        assert abs(float(np.linalg.norm(vector)) - 1.0) < 1e-5

    def test_is_deterministic_across_calls(self) -> None:
        assert hashing_embedding("dengue fever") == hashing_embedding("dengue fever")

    def test_different_texts_produce_different_vectors(self) -> None:
        assert hashing_embedding("glioma") != hashing_embedding("pneumonia")

    def test_empty_text_yields_a_zero_vector(self) -> None:
        vector = hashing_embedding("")
        assert all(value == 0.0 for value in vector)

    def test_lexical_overlap_retrieves_better_than_unrelated_text(self) -> None:
        query = hashing_embedding("blood pressure medication")
        related = hashing_embedding("blood pressure medication list")
        unrelated = hashing_embedding("fractured left ankle")

        assert cosine(query, related) > cosine(query, unrelated)

    def test_identical_text_scores_a_perfect_cosine(self) -> None:
        vector = hashing_embedding("paracetamol 650 mg")
        assert abs(cosine(vector, vector) - 1.0) < 1e-6


class TestEmbedEndpoint:
    def test_embeds_a_batch(self, client) -> None:
        response = client.post("/embed", json={"texts": ["glioma", "pneumonia"]})
        assert response.status_code == 200
        body = response.json()

        assert len(body["embeddings"]) == 2
        assert body["dim"] == EMBEDDING_DIM
        assert all(len(vector) == EMBEDDING_DIM for vector in body["embeddings"])
        assert body["inference_time_ms"] >= 0.0

    def test_reports_the_fallback_model_version(self, client) -> None:
        body = client.post("/embed", json={"texts": ["glioma"]}).json()
        assert body["model"] == "hashing-embed-v1.0"
        assert body["degraded"] is True

    def test_accepts_exactly_the_batch_cap(self, client) -> None:
        body = client.post("/embed", json={"texts": [f"text {i}" for i in range(100)]}).json()
        assert len(body["embeddings"]) == 100

    def test_rejects_a_batch_over_the_cap(self, client) -> None:
        response = client.post("/embed", json={"texts": [f"text {i}" for i in range(101)]})
        assert response.status_code == 422
        assert response.json()["error"] == "batch_too_large"

    def test_rejects_an_empty_batch(self, client) -> None:
        assert client.post("/embed", json={"texts": []}).status_code == 422

    def test_rejects_a_missing_field(self, client) -> None:
        assert client.post("/embed", json={}).status_code == 422

    def test_inference_is_logged(self, client, isolated_log) -> None:
        client.post("/embed", json={"texts": ["glioma"]})
        summary = isolated_log.per_model_summary()
        assert any(row["model_key"] == "hashing_embed" for row in summary)


@pytest.mark.heavy
class TestMiniLMBackend:
    def test_serves_semantic_embeddings_when_installed(self, client) -> None:
        from services.embed_service import SERVICE

        if not SERVICE._model.warm():
            pytest.skip("sentence-transformers / MiniLM weights are not installed")

        body = client.post("/embed", json={"texts": ["glioma", "pneumonia"]}).json()
        assert body["degraded"] is False
        assert body["model"] == "minilm-l6-v1.0"
        # Real semantics: these two are both medical terms, unlike the hashing
        # fallback which only sees lexical overlap.
        assert len(body["embeddings"][0]) == EMBEDDING_DIM
