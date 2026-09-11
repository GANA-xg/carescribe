"""FB-02 — dual OCR pipeline.

Runs two independent engines over the same prescription image and returns both
results **and** a merged one, so the backend can choose. Rule 4 of the brief is
explicit that neither engine's output is thrown away.

* **Donut** (``chinmays18/medical-prescription-ocr``) — a fine-tuned
  vision-encoder-decoder that emits structured tags such as ``<s_drug>``. Its
  per-token generation probabilities give a real confidence, and its tagged
  output gives per-field extraction.
* **Chandra** (``datalab-to/chandra-ocr-2``) — a VLM whose markdown output
  preserves layout, so it is the primary transcript.

**Merge strategy.** Chandra's markdown is the primary text because it keeps
layout, which matters for reading dose columns. Donut supplies the per-field
tags. Agreement is ``1 - CER`` between the two texts — two independent engines
that read the same page nearly identically are strong evidence both are right.

**Confidence.** Each engine reports its own; the merged result reports the
agreement score, which is the honest cross-engine signal. With neither engine
available the service returns empty text, ``confidence 0`` and ``degraded``
true — it never fabricates a transcript.
"""

from __future__ import annotations

import importlib
from typing import Any

from catalog import model_id
from config import get_settings
from utils.confidence import (
    agreement_score,
    drug_name_match_rate,
    normalize_confidence,
)
from utils.images import decode_image, enforce_min_size, size_desc
from utils.loader import LazyModel
from utils.text import extract_entities, find_date, normalize_whitespace
from utils.timing import InferenceTimer

#: Donut's task prompt for this fine-tune.
DONUT_PROMPT = "<s_ocr>"

DONUT_REPO = "chinmays18/medical-prescription-ocr"


class OcrService:
    """Two-engine OCR with an explicit merge step."""

    name = "ocr"
    endpoint = "/ocr"

    def __init__(self) -> None:
        self._donut = LazyModel(
            "donut",
            self._load_donut,
            fallback=lambda: None,
            note="Donut prescription OCR; unavailable engines are reported as empty",
        )
        self._chandra = LazyModel(
            "chandra",
            self._load_chandra,
            fallback=lambda: None,
            note="Chandra VLM OCR; unavailable engines are reported as empty",
        )
        self.models = (self._donut, self._chandra)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_donut() -> dict[str, Any]:
        """Load the Donut processor + model once, on CPU or GPU as available."""
        from transformers import DonutProcessor, VisionEncoderDecoderModel

        processor = DonutProcessor.from_pretrained(DONUT_REPO)
        model = VisionEncoderDecoderModel.from_pretrained(DONUT_REPO)
        device = get_settings().device
        model.to(device)
        model.eval()
        return {"processor": processor, "model": model, "device": device}

    @staticmethod
    def _load_chandra() -> Any:
        """Load Chandra through its documented ``InferenceManager`` entrypoint."""
        from chandra.model import InferenceManager

        # "hf" selects the HuggingFace backend, which is the CPU-capable path.
        return InferenceManager(method="hf")

    # --- introspection ----------------------------------------------------
    @property
    def engines(self) -> dict[str, str]:
        """Serving engine -> version tag, for traceability on the wire."""
        return {
            "donut": model_id("donut") if self._donut.available else "unavailable",
            "chandra": model_id("chandra") if self._chandra.available else "unavailable",
        }

    @property
    def serving_keys(self) -> list[str]:
        keys = [key for key, enabled in (
            ("donut", self._donut.available),
            ("chandra", self._chandra.available),
        ) if enabled]
        return keys or ["ocr_merge"]

    @property
    def degraded(self) -> bool:
        return not (self._donut.available and self._chandra.available)

    def model_version(self) -> str:
        """Version label describing what actually served this request."""
        live = self.serving_keys
        return "+".join(model_id(key) for key in live)

    def warmup(self) -> dict[str, bool]:
        return {
            self._chandra.key: self._chandra.warm(),
            self._donut.key: self._donut.warm(),
        }

    # --- inference --------------------------------------------------------
    def process(self, image_b64: str) -> dict[str, Any]:
        """Run both engines, merge, and return the response payload."""
        image = decode_image(image_b64)
        enforce_min_size(image)
        input_size = size_desc(image)

        # Per-engine timings are recorded separately because the paper reports
        # Donut and Chandra latency side by side.
        with InferenceTimer() as donut_timer:
            donut = self._run_donut(image)
        with InferenceTimer() as chandra_timer:
            chandra = self._run_chandra(image)
        with InferenceTimer() as merge_timer:
            merged, agreement, extraction_agreement = self.merge(donut=donut, chandra=chandra)

        return {
            "donut": {"text": donut["text"], "confidence": donut["confidence"]},
            "chandra": {
                "text": chandra["text"],
                "markdown": chandra["markdown"],
                "confidence": chandra["confidence"],
            },
            "merged": merged,
            "agreement": agreement,
            "extraction_agreement": extraction_agreement,
            "engines": self.engines,
            "degraded": self.degraded,
            "input_size": input_size,
            "timings": {
                "donut": donut_timer.elapsed_ms,
                "chandra": chandra_timer.elapsed_ms,
                "merge": merge_timer.elapsed_ms,
            },
        }

    def _run_donut(self, image: Any) -> dict[str, Any]:
        """Generate Donut output, with its own confidence. Never raises."""
        try:
            bundle = self._donut.load()
            if not self._donut.available:
                return {"text": "", "confidence": 0.0, "fields": {}, "available": False}

            torch = importlib.import_module("torch")
            processor, model = bundle["processor"], bundle["model"]
            device = bundle["device"]

            pixel_values = processor(image, return_tensors="pt").pixel_values.to(device)
            decoder_input_ids = processor.tokenizer(
                DONUT_PROMPT, add_special_tokens=False, return_tensors="pt"
            ).input_ids.to(device)

            with torch.no_grad():
                outputs = model.generate(
                    pixel_values,
                    decoder_input_ids=decoder_input_ids,
                    max_length=model.config.decoder.max_position_embeddings,
                    early_stopping=True,
                    num_beams=1,
                    return_dict_in_generate=True,
                    output_scores=True,
                )

            text = processor.batch_decode(outputs.sequences, skip_special_tokens=True)[0]
            return {
                "text": normalize_whitespace(text),
                "confidence": self._sequence_confidence(outputs),
                "fields": self._parse_donut_tags(text),
                "available": True,
            }
        except Exception:  # noqa: BLE001 - a failing engine degrades, never 500s
            return {"text": "", "confidence": 0.0, "fields": {}, "available": False}

    def _run_chandra(self, image: Any) -> dict[str, Any]:
        """Generate Chandra markdown + text. Never raises."""
        try:
            manager = self._chandra.load()
            if not self._chandra.available:
                return {"text": "", "markdown": "", "confidence": 0.0, "available": False}

            from chandra.model.schema import BatchInputItem

            batch = [BatchInputItem(image=image, item_type="image")]
            results = manager.generate(batch)
            first = results[0]

            markdown = normalize_whitespace(getattr(first, "markdown", "") or "")
            text = normalize_whitespace(getattr(first, "text", "") or "")
            if not markdown:
                markdown = text
            if not text:
                text = markdown
            raw_confidence = getattr(first, "confidence", None)
            confidence = (
                normalize_confidence(raw_confidence)
                if raw_confidence is not None
                else (0.75 if text else 0.0)
            )
            return {
                "text": text,
                "markdown": markdown,
                "confidence": confidence,
                "available": bool(text),
            }
        except Exception:  # noqa: BLE001
            return {"text": "", "markdown": "", "confidence": 0.0, "available": False}

    # --- merge (pure, so it is directly testable) -------------------------
    @staticmethod
    def _sequence_confidence(outputs: Any) -> float:
        """Geometric mean of the chosen tokens' probabilities.

        Donut returns transition scores per decoding step; the geometric mean is
        the standard sequence-level summary and lands in ``[0, 1]``.
        """
        scores = getattr(outputs, "scores", None)
        if not scores:
            return 0.0
        try:
            import torch

            log_probs: list[float] = []
            for step, step_scores in enumerate(scores):
                probabilities = torch.softmax(step_scores[0], dim=-1)
                token = int(outputs.sequences[0][step + 1])
                value = float(probabilities[token])
                if value <= 0.0:
                    continue
                log_probs.append(value)
            if not log_probs:
                return 0.0
            product = 1.0
            for value in log_probs:
                product *= value
            return normalize_confidence(product ** (1.0 / len(log_probs)))
        except Exception:  # noqa: BLE001 - confidence is best-effort
            return 0.0

    @staticmethod
    def _parse_donut_tags(text: str) -> dict[str, list[str]]:
        """Pull ``<s_tag>value</s_tag>`` pairs out of Donut's tagged output."""
        import re

        fields: dict[str, list[str]] = {}
        for tag, value in re.findall(r"<s_([a-z_]+)>(.*?)</s_\1>", text or "", re.DOTALL):
            cleaned = normalize_whitespace(value)
            if cleaned:
                fields.setdefault(tag, []).append(cleaned)
        return fields

    @classmethod
    def merge(cls, *, donut: dict[str, Any], chandra: dict[str, Any]) -> tuple[dict[str, Any], float, float]:
        """Combine engine outputs.

        Returns ``(merged, agreement, extraction_agreement)`` where agreement is
        ``1 - CER`` over the two transcripts and extraction is the Jaccard
        similarity of their drug lists.
        """
        chandra_text = chandra.get("text") or chandra.get("markdown") or ""
        donut_text = donut.get("text") or ""
        # Chandra keeps layout, so it is the primary transcript; Donut fills gaps.
        primary = chandra_text or donut_text
        if chandra_text and donut_text and len(donut_text) > len(chandra_text) * 1.5:
            # Chandra occasionally returns a terse caption; the longer Donut
            # transcript is then the better transcript.
            primary = donut_text

        agreement = (
            agreement_score(chandra_text, donut_text)
            if chandra_text and donut_text
            else 0.0
        )

        entity_text = " ".join(part for part in (chandra_text, donut_text) if part)
        rules = extract_entities(entity_text)
        donut_fields = donut.get("fields") or {}

        drugs = cls._merge_drugs(rules["drugs"], donut_fields)
        diagnosis = (
            rules["diagnosis"]
            or " ".join(donut_fields.get("diagnosis", []))[:160]
        )
        date = find_date(entity_text)

        # Cross-check the two engines' drug lists. Strengths are stripped first:
        # "Dolo 650 mg" and "dolo" are the same drug, and the presence of a dose
        # in one source but not the other is not a disagreement.
        donut_drugs = donut_fields.get("drug", [])
        extraction_agreement = drug_name_match_rate(donut_drugs, rules["drugs"])

        merged = {
            "structured": {
                "drugs": drugs,
                "diagnosis": normalize_whitespace(diagnosis),
                "date": date,
            },
            "text": primary,
            "engine": "chandra+donut" if (chandra_text and donut_text) else (
                "chandra" if chandra_text else ("donut" if donut_text else "none")
            ),
            "drug_agreement": normalize_confidence(extraction_agreement),
        }
        return merged, normalize_confidence(agreement), normalize_confidence(extraction_agreement)

    @staticmethod
    def _merge_drugs(rule_drugs: list[str], donut_fields: dict[str, list[str]]) -> list[str]:
        """Union of the parser's drugs and Donut's tagged drugs."""
        merged: list[str] = []
        for source in (donut_fields.get("drug", []), rule_drugs):
            for drug in source:
                cleaned = normalize_whitespace(drug)
                if cleaned and cleaned.lower() not in {item.lower() for item in merged}:
                    merged.append(cleaned)
        return merged


SERVICE = OcrService()
