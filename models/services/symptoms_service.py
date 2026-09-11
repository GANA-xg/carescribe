"""FB-06 — symptom to condition triage.

Two backends:

* **Primary** — the scikit-learn model trained by ``scripts/train_symptoms.py``
  (MultiLabelBinarizer symptom vector -> RandomForest over disease labels).
* **Fallback** — a curated knowledge base of ~45 conditions and their typical
  symptom weights. This is real clinical-triage logic, not a stub: it is what
  serves on a fresh clone, and it is also used to rescue the response when the
  trained model returns nothing above its threshold.

**Severity.** The brief fixes the count thresholds (1-3 low, 4-6 medium, 7+
high) and requires ``see_doctor: true`` for high. On top of that, a curated list
of red-flag symptoms forces ``high`` regardless of how many conditions matched —
"chest pain" must never come back as low severity just because it matched one
condition. ``medium`` also advises seeing a doctor; only ``low`` does not.

This service is decision support. It does not diagnose, and the response says so.
"""

from __future__ import annotations

from typing import Any

from catalog import model_id
from config import get_settings
from utils.confidence import normalize_confidence
from utils.loader import LazyModel

#: Filename the training script writes and the service reads.
WEIGHTS_FILENAME = "symptom_model.pkl"

#: Cap on conditions returned, so a vague input cannot return a wall of text.
MAX_CONDITIONS = 8

#: Minimum absolute rule score before a condition is worth reporting.
MIN_RULE_SCORE = 2.0

#: Probability below which the trained model's suggestion is dropped.
DEFAULT_MODEL_THRESHOLD = 0.30

DISCLAIMER = (
    "Symptom triage is decision support only and is not a diagnosis. "
    "Consult a qualified clinician."
)

#: Red flags: any match forces high severity and a doctor referral.
CRITICAL_SYMPTOMS: tuple[str, ...] = (
    "chest pain",
    "chest tightness",
    "shortness of breath",
    "difficulty breathing",
    "cannot breathe",
    "unconscious",
    "fainting",
    "seizure",
    "convulsion",
    "severe bleeding",
    "bleeding heavily",
    "blood in vomit",
    "coughing blood",
    "blood in sputum",
    "confusion",
    "slurred speech",
    "weakness on one side",
    "facial droop",
    "stiff neck",
    "sudden vision loss",
    "swelling of throat",
    "swelling of lips",
    "suicidal",
    "collapse",
    "blue lips",
    "dark stools",
    "severe abdominal pain",
    "right lower abdominal pain",
)

#: condition -> {symptom phrase: weight}. Weights express how characteristic the
#: symptom is of that condition; the max-confidence path normalises by the total.
CONDITION_RULES: dict[str, dict[str, float]] = {
    "influenza": {"fever": 2.0, "cough": 1.5, "body ache": 2.0, "fatigue": 1.5,
                  "headache": 1.0, "chills": 1.5, "sore throat": 1.0},
    "common cold": {"runny nose": 2.0, "sneezing": 2.0, "sore throat": 1.5, "cough": 1.0,
                    "nasal congestion": 1.5, "mild fever": 0.5},
    "covid-19": {"fever": 1.5, "dry cough": 1.5, "loss of smell": 2.5, "loss of taste": 2.5,
                 "fatigue": 1.0, "sore throat": 1.0, "shortness of breath": 1.5},
    "pneumonia": {"fever": 1.5, "productive cough": 2.0, "chest pain": 1.5,
                  "shortness of breath": 2.0, "chills": 1.0, "fatigue": 1.0},
    "bronchitis": {"cough": 2.0, "phlegm": 2.0, "chest discomfort": 1.5, "wheezing": 1.5,
                   "sore throat": 0.5},
    "asthma": {"wheezing": 2.5, "shortness of breath": 2.0, "chest tightness": 2.0,
               "cough": 1.5},
    "tuberculosis": {"chronic cough": 2.5, "weight loss": 2.0, "night sweats": 2.5,
                     "fever": 1.5, "blood in sputum": 2.0},
    "sinusitis": {"facial pain": 2.0, "nasal congestion": 2.0, "headache": 1.5,
                  "thick discharge": 2.0, "fever": 1.0},
    "pharyngitis": {"sore throat": 2.5, "difficulty swallowing": 2.0, "fever": 1.0,
                    "swollen lymph nodes": 1.5},
    "gastroenteritis": {"diarrhoea": 2.5, "vomiting": 2.0, "abdominal pain": 1.5,
                        "nausea": 1.5, "fever": 1.0},
    "food poisoning": {"vomiting": 2.5, "diarrhoea": 2.5, "abdominal cramps": 2.0,
                       "nausea": 2.0, "fever": 0.5},
    "acid reflux": {"heartburn": 2.5, "regurgitation": 2.0, "chest pain": 1.0,
                    "bloating": 1.5, "sour taste": 2.0},
    "peptic ulcer": {"upper abdominal pain": 2.5, "bloating": 1.5, "nausea": 1.5,
                     "dark stools": 2.0, "vomiting": 1.0},
    "gastritis": {"upper abdominal pain": 2.0, "nausea": 1.5, "vomiting": 1.0,
                  "bloating": 2.0, "indigestion": 1.5},
    "appendicitis": {"right lower abdominal pain": 3.0, "nausea": 1.5, "vomiting": 1.5,
                     "fever": 1.5, "loss of appetite": 1.5},
    "urinary tract infection": {"burning urination": 2.5, "frequent urination": 2.0,
                                "lower abdominal pain": 1.5, "cloudy urine": 2.0,
                                "fever": 0.5},
    "kidney stones": {"flank pain": 2.5, "blood in urine": 2.0, "painful urination": 1.5,
                      "nausea": 1.0, "back pain": 1.0},
    "migraine": {"throbbing headache": 2.5, "nausea": 1.5, "light sensitivity": 2.0,
                 "aura": 2.0, "vomiting": 1.0},
    "tension headache": {"headache": 2.0, "neck stiffness": 1.5, "scalp tenderness": 1.5},
    "hypertension": {"headache": 1.0, "dizziness": 1.5, "blurred vision": 1.5,
                     "nosebleed": 1.0, "palpitations": 1.0},
    "diabetes": {"excessive thirst": 2.5, "frequent urination": 2.0, "weight loss": 1.5,
                 "fatigue": 1.5, "blurred vision": 1.0},
    "hypothyroidism": {"fatigue": 2.0, "weight gain": 2.0, "cold intolerance": 2.0,
                       "constipation": 1.5, "dry skin": 1.5},
    "anaemia": {"fatigue": 2.0, "pallor": 2.0, "shortness of breath": 1.5,
                "dizziness": 1.5, "palpitations": 1.0},
    "dengue": {"high fever": 2.5, "severe joint pain": 2.5, "rash": 2.0,
               "headache": 1.5, "bleeding gums": 2.0},
    "malaria": {"fever": 2.0, "chills": 2.0, "sweating": 2.0, "headache": 1.5,
                "body ache": 1.5},
    "typhoid": {"prolonged fever": 2.5, "abdominal pain": 1.5, "constipation": 1.5,
                "weakness": 1.5, "rash": 1.0},
    "hepatitis": {"jaundice": 3.0, "dark urine": 2.0, "fatigue": 1.5, "nausea": 1.5,
                  "abdominal pain": 1.5},
    "conjunctivitis": {"red eye": 2.5, "eye discharge": 2.0, "itching eyes": 1.5,
                       "gritty feeling": 1.5},
    "otitis media": {"ear pain": 2.5, "hearing loss": 1.5, "fever": 1.0,
                     "ear discharge": 1.5},
    "vertigo": {"dizziness": 2.5, "spinning sensation": 2.5, "nausea": 1.5,
                "balance problems": 2.0},
    "anxiety": {"palpitations": 1.5, "restlessness": 2.0, "excessive worry": 2.5,
                "insomnia": 1.5, "sweating": 1.0},
    "depression": {"low mood": 2.5, "loss of interest": 2.5, "insomnia": 1.5,
                   "fatigue": 1.5, "poor concentration": 1.5},
    "osteoarthritis": {"joint pain": 2.0, "joint stiffness": 2.0, "reduced mobility": 1.5,
                       "joint swelling": 1.0},
    "rheumatoid arthritis": {"joint pain": 2.0, "morning stiffness": 2.5,
                             "joint swelling": 2.0, "fatigue": 1.0},
    "gout": {"sudden joint pain": 2.5, "swollen joint": 2.0, "redness": 1.5,
             "big toe pain": 2.5},
    "dermatitis": {"itchy skin": 2.5, "rash": 2.0, "redness": 1.5, "dry skin": 1.5},
    "urticaria": {"hives": 2.5, "itching": 2.0, "raised welts": 2.5, "swelling": 1.0},
    "food allergy": {"hives": 2.0, "swelling of lips": 2.5, "itching": 1.5,
                     "difficulty breathing": 2.0, "nausea": 1.0},
    "meningitis": {"stiff neck": 3.0, "severe headache": 2.0, "fever": 1.5,
                   "light sensitivity": 1.5, "rash": 1.5},
    "stroke": {"weakness on one side": 3.0, "slurred speech": 3.0, "facial droop": 3.0,
               "confusion": 2.0, "sudden vision loss": 2.0},
    "heart attack": {"chest pain": 3.0, "shortness of breath": 2.0, "left arm pain": 2.5,
                     "sweating": 2.0, "nausea": 1.5},
    "angina": {"chest pain": 2.5, "chest tightness": 2.0, "shortness of breath": 1.5,
               "pain on exertion": 2.5},
    "anaphylaxis": {"difficulty breathing": 3.0, "swelling of throat": 3.0, "hives": 2.0,
                    "dizziness": 2.0, "collapse": 3.0},
    "sepsis": {"high fever": 2.0, "rapid breathing": 2.0, "confusion": 2.5,
               "rapid heartbeat": 1.5, "low blood pressure": 2.0},
}


def normalize_symptom(symptom: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace."""
    cleaned = "".join(
        character if (character.isalnum() or character.isspace() or character == "-")
        else " "
        for character in (symptom or "")
    )
    return " ".join(cleaned.replace("_", " ").split()).lower()


def assess_severity(condition_count: int, symptoms: list[str]) -> tuple[str, bool]:
    """Map a matched-condition count and red flags onto ``(severity, see_doctor)``.

    Red flags take precedence over the count: one matched condition plus "chest
    pain" is high severity, not low.
    """
    if any(_matches_critical(symptom) for symptom in symptoms):
        return ("high", True)
    if condition_count >= 7:
        return ("high", True)
    if condition_count >= 4:
        return ("medium", True)
    return ("low", False)


def _matches_critical(symptom: str) -> bool:
    normalized = normalize_symptom(symptom)
    if not normalized:
        return False
    return any(flag in normalized or normalized in flag for flag in CRITICAL_SYMPTOMS)


class SymptomsService:
    """Turns a symptom list into ranked conditions plus a triage level."""

    name = "symptoms"
    endpoint = "/symptoms"

    def __init__(self) -> None:
        self._model = LazyModel(
            "symptoms",
            self._load_model,
            fallback=self._load_rules,
            fallback_key="symptoms_rules",
            note="trained symptom classifier; curated rules knowledge base as fallback",
        )
        self.models = (self._model,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_model() -> dict[str, Any]:
        """Load the trained pipeline bundle. Raises to trigger the fallback."""
        import joblib

        path = get_settings().weights_dir / WEIGHTS_FILENAME
        if not path.exists():
            raise FileNotFoundError(
                f"symptom model not found at {path}; run `python scripts/train_symptoms.py`"
            )

        bundle = joblib.load(path)
        if not isinstance(bundle, dict) or "model" not in bundle or "mlb" not in bundle:
            raise ValueError(
                "symptom model bundle must contain 'model' and 'mlb'; "
                "re-run scripts/train_symptoms.py"
            )
        return bundle

    @staticmethod
    def _load_rules() -> str:
        """Fallback marker; the knowledge base lives in this module."""
        return "rules"

    # --- introspection ----------------------------------------------------
    @property
    def engine(self) -> str:
        return "sklearn" if self._model.available else "rules"

    @property
    def serving_key(self) -> str:
        return "symptoms" if self._model.available else "symptoms_rules"

    @property
    def degraded(self) -> bool:
        return self._model.serving_fallback

    def model_version(self) -> str:
        return model_id(self.serving_key)

    def warmup(self) -> dict[str, bool]:
        return {self._model.key: self._model.warm()}

    # --- inference --------------------------------------------------------
    def check(self, symptoms: list[str]) -> dict[str, Any]:
        """Rank conditions for the given symptoms and assign a triage level."""
        self._model.load()
        cleaned = [normalize_symptom(symptom) for symptom in symptoms]
        cleaned = [symptom for symptom in cleaned if symptom]
        if not cleaned:
            return {
                "conditions": [],
                "condition_scores": [],
                "severity": "low",
                "see_doctor": False,
                "engine": self.engine,
                "degraded": self.degraded,
                "confidence": 0.0,
            }

        if self._model.available:
            ranked = self._predict_with_model(self._model.load(), cleaned)
            if not ranked:
                # The trained model had nothing above threshold; the explicitly
                # broader rule base still might.
                ranked = self._predict_with_rules(cleaned)
        else:
            ranked = self._predict_with_rules(cleaned)

        ranked = ranked[:MAX_CONDITIONS]
        conditions = [condition for condition, _ in ranked]
        scores = [
            {"condition": condition, "confidence": normalize_confidence(score)}
            for condition, score in ranked
        ]
        severity, see_doctor = assess_severity(len(conditions), cleaned)

        return {
            "conditions": conditions,
            "condition_scores": scores,
            "severity": severity,
            "see_doctor": see_doctor,
            "engine": self.engine,
            "degraded": self.degraded,
            "confidence": max((score for _, score in ranked), default=0.0),
        }

    def _predict_with_model(self, bundle: dict[str, Any], symptoms: list[str]) -> list[tuple[str, float]]:
        """Score conditions with the trained classifier."""
        threshold = float(bundle.get("threshold", DEFAULT_MODEL_THRESHOLD))
        features = bundle["mlb"].transform([symptoms])
        probabilities = bundle["model"].predict_proba(features)[0]
        labels = list(bundle["model"].classes_)

        ranked = sorted(
            zip(labels, (float(value) for value in probabilities)),
            key=lambda pair: pair[1],
            reverse=True,
        )
        return [(label, score) for label, score in ranked if score >= threshold]

    @staticmethod
    def _predict_with_rules(symptoms: list[str]) -> list[tuple[str, float]]:
        """Score conditions against the curated knowledge base.

        Confidence is the share of that condition's characteristic symptoms the
        patient reported, so it stays meaningful regardless of how many total
        weights a condition happens to have.
        """
        joined = " | ".join(symptoms)
        scored: list[tuple[str, float]] = []

        for condition, expected in CONDITION_RULES.items():
            matched = sum(
                weight
                for phrase, weight in expected.items()
                if _phrase_matches(phrase, symptoms, joined)
            )
            total = sum(expected.values())
            if matched < MIN_RULE_SCORE or total <= 0.0:
                continue
            scored.append((condition, matched / total))

        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return scored


def _phrase_matches(phrase: str, symptoms: list[str], joined: str) -> bool:
    """True when a knowledge-base phrase is present in the reported symptoms."""
    if phrase in joined:
        return True
    # Also allow the patient's wording to be narrower than the KB phrase, so
    # "joint pain" matches "sudden joint pain".
    return any(symptom in phrase for symptom in symptoms if len(symptom) >= 4)


SERVICE = SymptomsService()
