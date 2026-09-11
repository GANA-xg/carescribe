"""Confidence normalisation and error-rate metrics.

Rule 3 of the FreeBuff brief: never return a bare prediction without a
confidence. Every service therefore funnels its raw score through
:func:`normalize_confidence` so the number on the wire is always a real
probability in ``[0, 1]``.

The error-rate metrics here serve two masters: the FB-02 OCR agreement score at
runtime, and the FB-11 evaluation scripts (CER / WER against ground truth).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Sequence

from utils.text import comparable, normalize_drug_name

#: Guard so a pathological input cannot make the O(n*m) DP the bottleneck.
MAX_EDIT_LENGTH = 8000


def clamp01(value: float) -> float:
    """Clamp to ``[0, 1]``, mapping NaN/inf to ``0.0``."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(numeric) or math.isinf(numeric):
        return 0.0
    return max(0.0, min(1.0, numeric))


def normalize_confidence(value: float) -> float:
    """Round a clamped confidence to four decimals for a stable wire format."""
    return round(clamp01(value), 4)


def probability_distribution(scores: Sequence[float]) -> list[float]:
    """Turn arbitrary scores into a probability distribution summing to 1.

    Handles logits, unnormalised scores and already-normalised vectors, so a
    backend may hand over raw model output without pre-processing.
    """
    values = [float(s) for s in scores]
    if not values:
        return []
    if any(v < 0.0 for v in values):
        peak = max(values)
        values = [math.exp(v - peak) for v in values]  # softmax for logits
    total = sum(values)
    if total <= 0.0:
        return [round(1.0 / len(values), 6)] * len(values)
    return [round(v / total, 6) for v in values]


# --------------------------------------------------------------------------
# Edit distance and error rates
# --------------------------------------------------------------------------

def edit_distance(reference: str, hypothesis: str) -> int:
    """Levenshtein distance with a two-row rolling buffer."""
    ref, hyp = reference[:MAX_EDIT_LENGTH], hypothesis[:MAX_EDIT_LENGTH]
    if ref == hyp:
        return 0
    if not ref:
        return len(hyp)
    if not hyp:
        return len(ref)

    previous = list(range(len(hyp) + 1))
    for i, ref_char in enumerate(ref, start=1):
        current = [i]
        for j, hyp_char in enumerate(hyp, start=1):
            cost = 0 if ref_char == hyp_char else 1
            current.append(
                min(
                    previous[j] + 1,        # deletion
                    current[j - 1] + 1,     # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """CER = edit distance / reference length, after canonicalisation."""
    ref, hyp = comparable(reference), comparable(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return min(1.0, edit_distance(ref, hyp) / float(len(ref)))


def word_error_rate(reference: str, hypothesis: str) -> float:
    """WER computed over whitespace-separated tokens."""
    ref_words = comparable(reference).split()
    hyp_words = comparable(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    return min(1.0, edit_distance(ref_words, hyp_words) / float(len(ref_words)))


def agreement_score(reference: str, hypothesis: str) -> float:
    """FB-02 agreement: ``1 - CER`` between the two OCR engines' outputs.

    Two engines that read the same prescription nearly identically score close
    to 1.0, which is the service's proxy for "both models are confident".
    """
    return round(1.0 - character_error_rate(reference, hypothesis), 4)


def drug_extraction_accuracy(truth: Sequence[str], predicted: Sequence[str]) -> float:
    """Recall of exactly-matching drug strings against ground truth.

    Strict on purpose: used by FB-11 where the ground-truth file states exactly
    what a correct extraction looks like, strengths included.
    """
    truth_set = {item.strip().lower() for item in truth if item and item.strip()}
    if not truth_set:
        return 0.0
    predicted_set = {item.strip().lower() for item in predicted if item and item.strip()}
    return round(len(truth_set & predicted_set) / float(len(truth_set)), 4)


def drug_name_match_rate(truth: Sequence[str], predicted: Sequence[str]) -> float:
    """Agreement between two drug lists after stripping strengths and forms.

    ``["Dolo 650 mg"]`` and ``["dolo"]`` agree. Returns the Jaccard similarity of
    the normalised names, and ``0.0`` when neither side found anything — an
    empty comparison is no evidence, not perfect agreement.
    """
    left = {normalize_drug_name(item) for item in truth if item and item.strip()}
    right = {normalize_drug_name(item) for item in predicted if item and item.strip()}
    left.discard("")
    right.discard("")
    if not left and not right:
        return 0.0
    union = left | right
    return round(len(left & right) / float(len(union)), 4)


def sequence_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    """Jaccard similarity between two string collections."""
    left_set = {item.strip().lower() for item in left if item and item.strip()}
    right_set = {item.strip().lower() for item in right if item and item.strip()}
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    return round(len(left_set & right_set) / float(len(union)), 4) if union else 0.0


def top_class(labels: Sequence[str], probabilities: Sequence[float]) -> tuple[str, float]:
    """Highest-probability label, with a safe empty-input fallback."""
    if not labels or not probabilities:
        return ("unknown", 0.0)
    pairs = list(zip(labels, probabilities))
    label, score = max(pairs, key=lambda pair: float(pair[1]))
    return (str(label), normalize_confidence(score))


def most_common_label(values: Sequence[str]) -> str:
    """Mode of a label sequence; empty string for no input."""
    if not values:
        return ""
    return Counter(values).most_common(1)[0][0]
