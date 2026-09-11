"""FB-06 tests — the ``/symptoms`` contract and the triage knowledge base."""

from __future__ import annotations

import pytest

from services.symptoms_service import (
    CONDITION_RULES,
    CRITICAL_SYMPTOMS,
    MAX_CONDITIONS,
    assess_severity,
    normalize_symptom,
)
from services.symptoms_service import SERVICE as symptoms_service


class TestSeverityBands:
    """The count brackets come straight from the brief, so they are pinned."""

    def test_one_to_three_conditions_is_low(self) -> None:
        assert assess_severity(1, []) == ("low", False)
        assert assess_severity(3, []) == ("low", False)

    def test_four_to_six_conditions_is_medium(self) -> None:
        assert assess_severity(4, []) == ("medium", True)
        assert assess_severity(6, []) == ("medium", True)

    def test_seven_or_more_conditions_is_high(self) -> None:
        assert assess_severity(7, []) == ("high", True)
        assert assess_severity(20, []) == ("high", True)

    def test_a_red_flag_forces_high_even_with_one_condition(self) -> None:
        # The whole point of the override: "chest pain" must never read as low.
        assert assess_severity(1, ["chest pain"]) == ("high", True)
        assert assess_severity(0, ["Slurred speech"]) == ("high", True)

    def test_no_conditions_is_low(self) -> None:
        assert assess_severity(0, []) == ("low", False)


class TestKnowledgeBase:
    def test_the_knowledge_base_is_substantial(self) -> None:
        assert len(CONDITION_RULES) >= 40

    def test_every_condition_has_at_least_one_weighted_symptom(self) -> None:
        for condition, expected in CONDITION_RULES.items():
            assert expected, f"{condition} has no symptoms"
            assert all(weight > 0.0 for weight in expected.values()), condition

    def test_red_flag_list_covers_the_emergencies(self) -> None:
        for flag in ("chest pain", "shortness of breath", "slurred speech", "seizure"):
            assert flag in CRITICAL_SYMPTOMS

    def test_normalisation_handles_case_punctuation_and_underscores(self) -> None:
        assert normalize_symptom("  Chest_Pain!  ") == "chest pain"
        assert normalize_symptom("FEVER") == "fever"
        assert normalize_symptom("sore  throat") == "sore throat"
        assert normalize_symptom(None) == ""  # type: ignore[arg-type]

    def test_rules_rank_a_textbook_presentation_first(self) -> None:
        ranked = dict(symptoms_service._predict_with_rules(["wheezing", "shortness of breath"]))
        assert "asthma" in ranked
        assert ranked["asthma"] > 0.5

    def test_unrecognised_input_matches_nothing(self) -> None:
        assert symptoms_service._predict_with_rules(["feeling peculiar"]) == []


class TestSymptomsEndpoint:
    def test_ranks_conditions_with_descending_confidence(self, client) -> None:
        body = client.post(
            "/symptoms", json={"symptoms": ["wheezing", "shortness of breath", "chest tightness"]}
        ).json()

        assert "asthma" in body["conditions"]
        scores = [item["confidence"] for item in body["condition_scores"]]
        assert scores == sorted(scores, reverse=True)
        assert all(0.0 <= score <= 1.0 for score in scores)

    def test_red_flag_returns_high_severity_and_a_referral(self, client) -> None:
        body = client.post("/symptoms", json={"symptoms": ["chest pain"]}).json()
        assert body["severity"] == "high"
        assert body["see_doctor"] is True

    def test_mild_presentation_returns_low_severity(self, client) -> None:
        body = client.post("/symptoms", json={"symptoms": ["runny nose", "sneezing"]}).json()
        assert body["severity"] == "low"
        assert body["see_doctor"] is False
        assert body["conditions"]

    def test_unrecognised_symptoms_return_no_conditions(self, client) -> None:
        body = client.post("/symptoms", json={"symptoms": ["feeling peculiar"]}).json()
        assert body["conditions"] == []
        assert body["condition_scores"] == []
        assert body["severity"] == "low"
        assert body["see_doctor"] is False

    def test_never_returns_more_than_the_cap(self, client) -> None:
        body = client.post(
            "/symptoms",
            json={
                "symptoms": [
                    "fever", "cough", "headache", "nausea", "vomiting", "fatigue",
                    "diarrhoea", "rash", "dizziness", "joint pain",
                ]
            },
        ).json()
        assert len(body["conditions"]) <= MAX_CONDITIONS

    def test_carries_a_disclaimer_and_reports_the_rules_engine(self, client) -> None:
        body = client.post("/symptoms", json={"symptoms": ["fever", "cough"]}).json()
        assert "not a diagnosis" in body["disclaimer"]
        assert body["engine"] == "rules"
        assert body["degraded"] is True
        assert body["model_version"] == "symptoms-rules-v1.0"

    def test_reports_version_and_latency(self, client) -> None:
        body = client.post("/symptoms", json={"symptoms": ["fever"]}).json()
        assert body["inference_time_ms"] >= 0.0
        assert body["model_version"]

    def test_duplicate_and_messy_symptoms_are_normalised(self, client) -> None:
        messy = client.post(
            "/symptoms", json={"symptoms": ["Chest_Pain!", "chest pain", "  CHEST   PAIN "]}
        ).json()
        assert messy["severity"] == "high"

    def test_empty_symptom_list_is_rejected(self, client) -> None:
        assert client.post("/symptoms", json={"symptoms": []}).status_code == 422

    def test_missing_field_is_rejected(self, client) -> None:
        assert client.post("/symptoms", json={}).status_code == 422


@pytest.mark.heavy
class TestTrainedModel:
    def test_serves_the_trained_classifier_when_present(self, client) -> None:
        if not symptoms_service._model.warm():
            pytest.skip("symptom_model.pkl is not installed")

        body = client.post("/symptoms", json={"symptoms": ["fever", "cough"]}).json()
        assert body["engine"] == "sklearn"
        assert body["degraded"] is False
        assert body["conditions"]
