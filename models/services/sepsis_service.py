"""FB-07 — sepsis risk scoring.

Five SOFA-inspired features: temperature, heart rate, respiratory rate, white
cell count and lactate. Target: sepsis onset within six hours (the label the
training script builds).

Two backends:

* **Primary** — XGBoost trained by ``scripts/train_sepsis.py``, explained with
  ``shap.TreeExplainer`` so every score comes with signed per-feature
  contributions. This is what the paper reports.
* **Fallback** — a transparent logistic model with published-style coefficients,
  used when xgboost/shap or the checkpoint are missing. Contributions are then
  ``coefficient x deviation from baseline``, which is a *linear* attribution, not
  SHAP. The response says which via ``explanation_method`` rather than passing one
  off as the other.

Risk score is ``probability x 100``. Bands follow the brief: below 30 low,
30 to 60 medium, above 60 high.

Neither backend is a validated clinical device. This is decision support for a
student project, and the response is shaped for a human to review.
"""

from __future__ import annotations

import math
from typing import Any

from catalog import model_id
from config import get_settings
from utils.confidence import clamp01, normalize_confidence
from utils.loader import LazyModel

WEIGHTS_FILENAME = "sepsis_model.pkl"

#: Feature order is fixed: it must match the training matrix column order.
FEATURES: tuple[str, ...] = ("temp", "hr", "rr", "wbc", "lactate")

#: Healthy-adult reference values the fallback measures deviation against.
BASELINE: dict[str, float] = {
    "temp": 37.0,
    "hr": 80.0,
    "rr": 16.0,
    "wbc": 8.0,
    "lactate": 1.0,
}

#: Intercept and per-feature weights for the fallback logistic model. Derived
#: from the direction and rough magnitude of the qSOFA/SOFA criteria, not fitted
#: to a cohort, so the fallback's calibration is approximate by construction.
FALLBACK_INTERCEPT = -2.2

#: Feature -> (direction, weight, threshold). ``direction`` selects whether risk
#: rises above the threshold, below it, or in either direction.
FALLBACK_WEIGHTS: dict[str, tuple[str, float, float]] = {
    "temp": ("deviation", 0.60, 1.0),     # fever above 38, hypothermia below 36
    "hr": ("above", 0.025, 90.0),         # tachycardia
    "rr": ("above", 0.150, 22.0),         # tachypnoea
    "wbc": ("either", 0.120, 12.0),       # leukocytosis or leukopenia
    "lactate": ("above", 1.100, 2.0),     # tissue hypoperfusion
}

RISK_MEDIUM = 30.0
RISK_HIGH = 60.0


def risk_level_for(score: float) -> str:
    """Band a 0-100 score: below 30 low, 30-60 medium, above 60 high."""
    if score > RISK_HIGH:
        return "high"
    if score >= RISK_MEDIUM:
        return "medium"
    return "low"


class SepsisService:
    """Scores sepsis risk from five vitals and explains the drivers."""

    name = "sepsis"
    endpoint = "/sepsis-risk"

    def __init__(self) -> None:
        self._model = LazyModel(
            "sepsis",
            self._load_model,
            fallback=self._load_heuristic,
            fallback_key="sepsis_heuristic",
            note="XGBoost sepsis classifier with TreeSHAP; transparent logistic fallback",
        )
        self.models = (self._model,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_model() -> dict[str, Any]:
        """Load the trained classifier and build its TreeSHAP explainer."""
        import joblib

        path = get_settings().weights_dir / WEIGHTS_FILENAME
        if not path.exists():
            raise FileNotFoundError(
                f"sepsis model not found at {path}; run `python scripts/train_sepsis.py`"
            )

        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or "model" not in bundle:
            raise ValueError("sepsis bundle must contain 'model'; re-run the training script")

        import shap

        explainer = shap.TreeExplainer(bundle["model"])
        return {**bundle, "explainer": explainer}

    @staticmethod
    def _load_heuristic() -> str:
        """Fallback marker; the logistic model lives in this module."""
        return "logistic"

    # --- introspection ----------------------------------------------------
    @property
    def engine(self) -> str:
        return "xgboost" if self._model.available else "logistic"

    @property
    def serving_key(self) -> str:
        return "sepsis" if self._model.available else "sepsis_heuristic"

    @property
    def degraded(self) -> bool:
        return self._model.serving_fallback

    def model_version(self) -> str:
        return model_id(self.serving_key)

    def warmup(self) -> dict[str, bool]:
        return {self._model.key: self._model.warm()}

    # --- inference --------------------------------------------------------
    def score(self, vitals: dict[str, float]) -> dict[str, Any]:
        """Return risk score, band, per-feature contributions and a summary."""
        self._model.load()
        values = {name: float(vitals[name]) for name in FEATURES}

        if self._model.available:
            result = self._score_with_model(self._model.load(), values)
            method = "shap"
        else:
            result = self._score_with_fallback(values)
            method = "linear-contribution"

        result["engine"] = self.engine
        result["degraded"] = self.degraded
        result["explanation_method"] = method
        result["explanation"] = self._explain(result["shap_values"], result["risk_level"])
        return result

    def _score_with_model(self, bundle: dict[str, Any], values: dict[str, float]) -> dict[str, Any]:
        """Score and explain with XGBoost + TreeSHAP."""
        import numpy as np

        feature_order = list(bundle.get("features", FEATURES))
        row = np.array([[values[name] for name in feature_order]], dtype=np.float32)

        model = bundle["model"]
        probability = float(model.predict_proba(row)[0][1])
        score = round(clamp01(probability) * 100.0, 2)

        contributions = self._shap_contributions(bundle["explainer"], row, feature_order)
        return {
            "risk_score": score,
            "risk_level": risk_level_for(score),
            "shap_values": contributions,
        }

    @staticmethod
    def _shap_contributions(explainer: Any, row: Any, feature_order: list[str]) -> list[dict[str, Any]]:
        """Signed SHAP value per feature, normalised across SHAP API versions."""
        import numpy as np

        raw = explainer.shap_values(row)
        array = np.asarray(raw, dtype=np.float64)

        # Binary classifiers return either (n, features) or (n, features, 2);
        # multi-output returns a list. Reduce to one value per feature.
        if array.ndim == 3:
            array = array[0, :, -1]
        elif array.ndim == 2:
            array = array[0]
        elif isinstance(raw, list) and raw:
            array = np.asarray(raw[-1], dtype=np.float64).reshape(-1)

        contributions = []
        for name, value in zip(feature_order, array.reshape(-1)):
            contributions.append(
                {
                    "feature": name,
                    "value": round(float(row[0][feature_order.index(name)]), 4),
                    "impact": round(float(value), 4),
                }
            )
        contributions.sort(key=lambda item: abs(item["impact"]), reverse=True)
        return contributions

    @staticmethod
    def _score_with_fallback(values: dict[str, float]) -> dict[str, Any]:
        """Transparent logistic scoring with linear per-feature attribution."""
        logit = FALLBACK_INTERCEPT
        contributions: list[dict[str, Any]] = []

        for name in FEATURES:
            value = values[name]
            direction, weight, threshold = FALLBACK_WEIGHTS[name]
            contribution = _fallback_contribution(name, value, direction, weight, threshold)
            logit += contribution
            contributions.append(
                {"feature": name, "value": round(value, 4), "impact": round(contribution, 4)}
            )

        probability = 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, logit))))
        score = round(clamp01(probability) * 100.0, 2)
        contributions.sort(key=lambda item: abs(item["impact"]), reverse=True)
        return {
            "risk_score": score,
            "risk_level": risk_level_for(score),
            "shap_values": contributions,
        }

    @staticmethod
    def _explain(contributions: list[dict[str, Any]], level: str) -> str:
        """One-sentence summary naming the features that moved the score most."""
        if not contributions:
            return f"Risk band: {level}. No feature attributions available."
        driving = [item for item in contributions[:3] if item["impact"] > 0.0]
        if not driving:
            return f"Risk band: {level}. No single feature raised the score."
        rendered = ", ".join(
            f"{item['feature']} {item['value']}"
            for item in driving
        )
        return f"Risk band: {level}. Largest contributors: {rendered}."


def _fallback_contribution(
    name: str, value: float, direction: str, weight: float, threshold: float
) -> float:
    """Log-odds contribution of one vital, honouring its risk direction."""
    if direction == "above":
        return weight * max(0.0, value - threshold)
    if direction == "below":
        return weight * max(0.0, threshold - value)
    if direction == "either":
        # Leukocytosis or leukopenia are both adverse.
        if value > threshold:
            return weight * (value - threshold)
        return weight * max(0.0, BASELINE[name] * 0.5 - value) * 1.5
    # "deviation": fever and hypothermia are both adverse for temperature.
    baseline = BASELINE[name]
    if value >= baseline:
        return weight * max(0.0, value - 38.0)
    return weight * max(0.0, 36.0 - value)


SERVICE = SepsisService()


__all__ = [
    "FEATURES",
    "BASELINE",
    "FALLBACK_WEIGHTS",
    "RISK_HIGH",
    "RISK_MEDIUM",
    "risk_level_for",
    "SERVICE",
]
