"""FB-03 tests — the ``/ner`` contract and the prescription parser."""

from __future__ import annotations

import pytest

from utils.text import extract_entities, find_dosages, find_drugs, find_frequencies


class TestRegexExtraction:
    """The fallback backend is real logic, so it gets real assertions."""

    def test_lexicon_drugs_are_found_case_insensitively(self) -> None:
        found = find_drugs("Tab PARACETAMOL 500mg and tab paracetamol 500 mg")
        assert found == ["paracetamol"]

    def test_unseen_brand_is_recovered_from_a_dose_line(self) -> None:
        # "Zylofast" is not in the lexicon; the dose-bearing line recovers it.
        result = extract_entities("Tab. Zylofast 250 mg BD")
        assert "zylofast" in result["drugs"]

    def test_spurious_words_are_not_treated_as_drugs(self) -> None:
        result = extract_entities("Patient name Ravi date 12 review after 5 days")
        assert result["drugs"] == []

    def test_dosages_are_captured_with_units(self) -> None:
        assert find_dosages("Augmentin 625 mg and 5 ml syrup") == ["625 mg", "5 ml"]

    def test_bare_strength_is_captured_when_no_unit_present(self) -> None:
        assert find_dosages("Tab Dolo 650 twice daily") == ["650"]

    def test_abbreviations_expand_to_canonical_frequencies(self) -> None:
        assert find_frequencies("Dolo 650 BD") == ["twice daily"]
        assert find_frequencies("cetirizine HS") == ["at bedtime"]

    def test_dose_pattern_is_not_reported_as_a_frequency(self) -> None:
        # "1-0-1" is a dose pattern, not a named frequency; it is excluded so the
        # frequency field stays a clean clinical vocabulary.
        assert "dose pattern" not in find_frequencies("Dolo 1-0-1")

    def test_diagnosis_label_is_extracted_and_trimmed(self) -> None:
        result = extract_entities("Diagnosis: Acute pharyngitis\nRx Dolo 650")
        assert result["diagnosis"] == "Acute pharyngitis"

    def test_condition_lexicon_is_used_when_unlabelled(self) -> None:
        result = extract_entities("Patient has hypertension since 2019")
        assert result["diagnosis"] == "hypertension"

    def test_full_prescription_round_trip(self, sample_prescription_text: str) -> None:
        result = extract_entities(sample_prescription_text)
        lowered = [drug.lower() for drug in result["drugs"]]
        assert "dolo" in lowered
        assert "augmentin" in lowered
        assert "cetrizine" in lowered
        assert result["dosages"] == ["650 mg", "625 mg", "5 ml"]
        assert result["diagnosis"] == "Acute pharyngitis"


class TestNerEndpoint:
    def test_extracts_structured_fields(self, client, sample_prescription_text: str) -> None:
        response = client.post("/ner", json={"text": sample_prescription_text})
        assert response.status_code == 200
        body = response.json()

        assert body["drugs"]
        assert body["dosages"] == ["650 mg", "625 mg", "5 ml"]
        assert "twice daily" in body["frequencies"]
        assert body["diagnosis"] == "Acute pharyngitis"

    def test_reports_version_latency_and_confidence(self, client, sample_prescription_text: str) -> None:
        body = client.post("/ner", json={"text": sample_prescription_text}).json()

        assert body["model_version"]
        assert body["inference_time_ms"] >= 0.0
        assert 0.0 <= body["confidence"] <= 1.0

    def test_declares_itself_degraded_without_medspacy(self, client) -> None:
        """With heavy models disabled the fallback serves, and says so."""
        body = client.post("/ner", json={"text": "Tab Dolo 650 mg BD"}).json()
        assert body["engine"] == "regex"
        assert body["degraded"] is True
        assert body["model_version"] == "ner-regex-v1.0"

    def test_empty_text_is_valid_and_returns_no_entities(self, client) -> None:
        body = client.post("/ner", json={"text": ""}).json()
        assert body["drugs"] == []
        assert body["confidence"] == 0.0

    def test_missing_text_field_is_rejected(self, client) -> None:
        assert client.post("/ner", json={}).status_code == 422

    def test_inference_is_recorded_in_the_log(self, client, isolated_log) -> None:
        client.post("/ner", json={"text": "Tab Dolo 650 mg BD"})
        summary = isolated_log.per_model_summary()
        assert any(row["model_key"] == "ner_regex" for row in summary)


@pytest.mark.heavy
class TestMedspacyBackend:
    """Only runs where medspaCy and a clinical pipeline are installed."""

    def test_real_pipeline_serves_when_available(self, client) -> None:
        from services.ner_service import SERVICE

        if SERVICE._nlp.load() and not SERVICE._nlp.available:
            pytest.skip("medspaCy pipeline not installed")

        body = client.post("/ner", json={"text": "Tab Dolo 650 mg BD"}).json()
        assert body["engine"] == "medspacy"
        assert body["degraded"] is False
