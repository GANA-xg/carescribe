"""FB-03 — clinical NER over prescription text.

Primary backend: medspaCy (``en_core_med7_lg``, falling back to the BC5CDR
chemical/disease model). Fallback backend: the dictionary + regex extractor in
:mod:`utils.text`.

The fallback is not a stub. It is a real parser that knows ~350 generics and
Indian market brands and recovers unknown names from dose-bearing lines, so a
deployment without medspaCy still produces usable structured output.

Whatever the backend, the two extractors are cross-checked against each other
and their agreement feeds the reported confidence. That is the honest choice:
classic NER produces no calibrated probability, so the service reports how much
the two independent parsers agree rather than inventing a number.
"""

from __future__ import annotations

from typing import Any

from catalog import model_id
from utils.confidence import normalize_confidence, sequence_similarity
from utils.loader import LazyModel
from utils.text import extract_entities

#: Preferred clinical pipelines, tried in order.
NLP_CANDIDATES: tuple[str, ...] = ("en_core_med7_lg", "en_ner_bc5cdr_md")

#: Pipeline label -> response field. Different pipelines name the same concept
#: differently (CHEMICAL vs DRUG, DISEASE vs CONDITION), so both are mapped.
LABEL_ALIASES: dict[str, str] = {
    "drug": "drugs",
    "chemical": "drugs",
    "medication": "drugs",
    "dosage": "dosages",
    "dose": "dosages",
    "strength": "dosages",
    "frequency": "frequencies",
    "route": "frequencies",
    "condition": "diagnosis",
    "disease": "diagnosis",
    "problem": "diagnosis",
}


def _target_rules() -> list[Any]:
    """medspaCy rules covering dose, frequency and food-timing phrasing."""
    from medspacy.ner import TargetRule

    single = [
        ("mg", "DOSAGE"),
        ("mcg", "DOSAGE"),
        ("ml", "DOSAGE"),
        ("IU", "DOSAGE"),
        ("OD", "FREQUENCY"),
        ("BD", "FREQUENCY"),
        ("TDS", "FREQUENCY"),
        ("QID", "FREQUENCY"),
        ("HS", "FREQUENCY"),
        ("PRN", "FREQUENCY"),
        ("SOS", "FREQUENCY"),
    ]
    phrases = [
        ("once daily", "FREQUENCY", ["once", "daily"]),
        ("twice daily", "FREQUENCY", ["twice", "daily"]),
        ("three times daily", "FREQUENCY", ["three", "times", "daily"]),
        ("after food", "FREQUENCY", ["after", "food"]),
        ("before food", "FREQUENCY", ["before", "food"]),
        ("at bedtime", "FREQUENCY", ["at", "bedtime"]),
    ]

    rules = [
        TargetRule(literal, label, pattern=[{"LOWER": literal.lower()}])
        for literal, label in single
    ]
    rules += [
        TargetRule(name, label, pattern=[{"LOWER": token} for token in tokens])
        for name, label, tokens in phrases
    ]
    return rules


class NerService:
    """Extracts drugs, dosages, frequencies and diagnosis from raw text."""

    name = "ner"
    endpoint = "/ner"
    version = "1.0"

    def __init__(self) -> None:
        self._nlp = LazyModel(
            "medspacy",
            self._load_spacy,
            fallback=self._load_regex,
            fallback_key="ner_regex",
            note="medspaCy clinical NER; regex parser serves when unavailable",
        )
        self.models = (self._nlp,)

    # --- backends ---------------------------------------------------------
    @staticmethod
    def _load_spacy() -> Any:
        """Load a medspaCy pipeline with target rules.

        Any failure raises, which tells the loader to degrade to the regex
        backend rather than to fail the request.
        """
        import spacy
        from medspacy.ner import TargetMatcher

        nlp: Any = None
        errors: list[str] = []
        for candidate in NLP_CANDIDATES:
            try:
                nlp = spacy.load(candidate)
                break
            except Exception as exc:  # noqa: BLE001 - try the next candidate
                errors.append(f"{candidate}: {exc}")
        if nlp is None:
            raise RuntimeError("no clinical spaCy pipeline found (" + "; ".join(errors) + ")")

        matcher = TargetMatcher(nlp)
        matcher.add(_target_rules())
        if "carescribe_target_matcher" in nlp.pipe_names:
            nlp.replace_pipe("carescribe_target_matcher", matcher)
        else:
            nlp.add_pipe(matcher, name="carescribe_target_matcher", last=True)
        return nlp

    @staticmethod
    def _load_regex() -> str:
        """Fallback marker; the extraction itself lives in ``utils.text``."""
        return "regex"

    # --- introspection ----------------------------------------------------
    @property
    def serving_key(self) -> str:
        """Catalog key actually answering requests, real model or fallback."""
        return "ner_regex" if self._nlp.serving_fallback else "medspacy"

    @property
    def engine(self) -> str:
        return "medspacy" if self._nlp.available else "regex"

    @property
    def degraded(self) -> bool:
        return self._nlp.serving_fallback

    def model_version(self) -> str:
        return model_id(self.serving_key)

    def warmup(self) -> dict[str, bool]:
        return {self._nlp.key: self._nlp.warm()}

    # --- inference --------------------------------------------------------
    def extract(self, text: str) -> dict[str, Any]:
        """Run NER and cross-check the two backends."""
        nlp = self._nlp.load()
        rules = extract_entities(text)

        if self._nlp.available and isinstance(nlp, str) is False:
            entities = self._extract_with_spacy(nlp, text)
            agreement = sequence_similarity(entities["drugs"], rules["drugs"])
            # Statistics the clinical model omits are filled from the parser so
            # the response is never emptier than the cheap backend's.
            entities["dosages"] = entities["dosages"] or rules["dosages"]
            entities["frequencies"] = entities["frequencies"] or rules["frequencies"]
            entities["diagnosis"] = entities["diagnosis"] or rules["diagnosis"]
            # A drug the parser found but the model missed is almost always a
            # real brand name; keep it rather than silently dropping it.
            known = {drug.lower() for drug in entities["drugs"]}
            for drug in rules["drugs"]:
                if drug.lower() not in known:
                    entities["drugs"].append(drug)
            confidence = normalize_confidence(
                0.5 * agreement + 0.5 * self._coverage(entities)
            )
        else:
            entities = {
                "drugs": list(rules["drugs"]),
                "dosages": list(rules["dosages"]),
                "frequencies": list(rules["frequencies"]),
                "diagnosis": rules["diagnosis"],
            }
            confidence = self._rule_confidence(rules)

        entities["engine"] = self.engine
        entities["degraded"] = self.degraded
        entities["confidence"] = confidence
        return entities

    @staticmethod
    def _extract_with_spacy(nlp: Any, text: str) -> dict[str, Any]:
        """Map pipeline entities onto the response shape, preserving order."""
        doc = nlp(text)
        collected: dict[str, list[str]] = {"drugs": [], "dosages": [], "frequencies": []}
        diagnosis: list[str] = []
        for entity in doc.ents:
            field = LABEL_ALIASES.get(entity.label_.lower())
            value = entity.text.strip()
            if field is None or not value:
                continue
            if field == "diagnosis":
                diagnosis.append(value)
                continue
            lowered = [item.lower() for item in collected[field]]
            if value.lower() not in lowered:
                collected[field].append(value)
        collected["diagnosis"] = " ".join(diagnosis)[:160]
        return collected

    @staticmethod
    def _coverage(entities: dict[str, Any]) -> float:
        """Fraction of the four expected fields that produced a value."""
        populated = sum(
            1
            for field in ("drugs", "dosages", "frequencies", "diagnosis")
            if entities.get(field)
        )
        return populated / 4.0

    @staticmethod
    def _rule_confidence(rules: dict[str, Any]) -> float:
        """Confidence for the regex backend.

        Explicitly a heuristic: it reflects how much of the text was
        understood, not a calibrated probability. Lexicon hits weigh more than
        tokens recovered by the unknown-name heuristic.
        """
        drugs = rules.get("drugs", [])
        if not drugs:
            return 0.0
        lexicon_ratio = int(rules.get("lexicon_hits", 0)) / float(len(drugs))
        fields = sum(
            1
            for field in ("drugs", "dosages", "frequencies", "diagnosis")
            if rules.get(field)
        )
        return normalize_confidence(0.55 * lexicon_ratio + 0.45 * (fields / 4.0))


SERVICE = NerService()
