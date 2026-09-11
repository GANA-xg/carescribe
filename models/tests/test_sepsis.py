"""FB-07 tests — the ``/sepsis-risk`` contract and the transparent fallback."""

from __future__ import annotations

import pytest

from services.sepsis_service import (
    FEATURES,
    RISK_HIGH,
    RISK_MEDIUM,
    SERVICE as sepsis_service,
    risk_level_for,
)

#: A healthy adult: every feature inside its reference range.
NORMAL = {"temp": 37.0, "hr": 80.0, "rr": 16.0, "wbc": 8.0, "lactate": 1.0}

#: Frank septic shock physiology.
SEPTIC = {"temp": 39.5, "hr": 120.0, "rr": 30.0, "wbc": 18.0, "lactate": 4.0}


def score(vitals: dict[str, float]) -> float:
    return float(sepsis_service.score(vitals)["risk_score"])


class TestRiskBands:
    """The band boundaries come from the brief, so they are pinned exactly."""

    def test_below_thirty_is_low(self) -> None:
        assert risk_level_for(0.0) == "low"
        assert risk_level_for(29.99) == "low"

    def test_thirty_to_sixty_is_medium(self) -> None:
        assert risk_level_for(RISK_MEDIUM) == "medium"
        assert risk_level_for(45.0) == "medium"
        assert risk_level_for(RISK_HIGH) == "medium"

    def test_above_sixty_is_high(self) -> None:
        assert risk_level_for(60.01) == "high"
        assert risk_level_for(100.0) == "high"


class TestFallbackScoring:
    def test_healthy_vitals_score_low(self) -> None:
        result = sepsis_service.score(NORMAL)
        assert result["risk_score"] < RISK_MEDIUM
        assert result["risk_level"] == "low"

    def test_septic_vitals_score_high(self) -> None:
        result = sepsis_service.score(SEPTIC)
        assert result["risk_score"] > RISK_HIGH
        assert result["risk_level"] == "high"

    def test_score_stays_within_bounds_for_extreme_input(self) -> None:
        extreme = {"temp": 43.0, "hr": 400.0, "rr": 90.0, "wbc": 90.0, "lactate": 40.0}
        assert 0.0 <= score(extreme) <= 100.0

    def test_rising_lactate_raises_the_score_monotonically(self) -> None:
        scores = [score({**NORMAL, "lactate": value}) for value in (1.0, 2.0, 3.0, 4.0, 6.0)]
        assert scores == sorted(scores)
        assert scores[-1] > scores[0]

    def test_tachycardia_and_tachypnoea_both_raise_the_score(self) -> None:
        assert score({**NORMAL, "hr": 130.0}) > score(NORMAL)
        assert score({**NORMAL, "rr": 32.0}) > score(NORMAL)

    def test_fever_and_hypothermia_both_raise_the_score(self) -> None:
        # Sepsis presents with either, so a low temperature must not look safe.
        assert score({**NORMAL, "temp": 39.5}) > score(NORMAL)
        assert score({**NORMAL, "temp": 34.5}) > score(NORMAL)

    def test_leukopenia_raises_the_score_as_well_as_leucocytosis(self) -> None:
        assert score({**NORMAL, "wbc": 19.0}) > score(NORMAL)
        assert score({**NORMAL, "wbc": 2.0}) > score(NORMAL)

    def test_all_five_features_are_attributed(self) -> None:
        result = sepsis_service.score(SEPTIC)
        assert [item["feature"] for item in result["shap_values"]] == sorted(
            FEATURES, key=lambda name: -abs(next(
                item["impact"] for item in result["shap_values"] if item["feature"] == name
            ))
        )
        assert {item["feature"] for item in result["shap_values"]} == set(FEATURES)

    def test_contributions_are_ordered_by_magnitude(self) -> None:
        impacts = [abs(item["impact"]) for item in sepsis_service.score(SEPTIC)["shap_values"]]
        assert impacts == sorted(impacts, reverse=True)

    def test_healthy_vitals_produce_no_positive_contributions(self) -> None:
        impacts = [item["impact"] for item in sepsis_service.score(NORMAL)["shap_values"]]
        assert all(impact <= 0.0 for impact in impacts)

    def test_explanation_names_the_band_and_the_driving_features(self) -> None:
        result = sepsis_service.score(SEPTIC)
        assert "high" in result["explanation"]
        assert "lactate" in result["explanation"]

    def test_declares_the_linear_attribution_method(self) -> None:
        assert sepsis_service.score(SEPTIC)["explanation_method"] == "linear-contribution"
        assert sepsis_service.score(SEPTIC)["engine"] == "logistic"


class TestSepsisEndpoint:
    def test_returns_the_full_contract(self, client) -> None:
        response = client.post("/sepsis-risk", json={"vitals": SEPTIC})
        assert response.status_code == 200
        body = response.json()

        assert 0.0 <= body["risk_score"] <= 100.0
        assert body["risk_level"] == "high"
        assert body["shap_values"]
        assert set(body["shap_values"][0]) == {"feature", "value", "impact"}
        assert body["explanation"]
        assert body["model_version"] == "sepsis-qsofa-v1.0"
        assert body["inference_time_ms"] >= 0.0

    def test_healthy_patient_returns_low_risk(self, client) -> None:
        body = client.post("/sepsis-risk", json={"vitals": NORMAL}).json()
        assert body["risk_level"] == "low"

    def test_reports_the_fallback_honestly(self, client) -> None:
        body = client.post("/sepsis-risk", json={"vitals": NORMAL}).json()
        assert body["degraded"] is True
        assert body["explanation_method"] == "linear-contribution"

    @pytest.mark.parametrize("missing", list(FEATURES))
    def test_each_vital_is_required(self, client, missing: str) -> None:
        incomplete = {key: value for key, value in SEPTIC.items() if key != missing}
        assert client.post("/sepsis-risk", json={"vitals": incomplete}).status_code == 422

    def test_vitals_must_be_numeric(self, client) -> None:
        payload = {**SEPTIC, "lactate": "high"}
        assert client.post("/sepsis-risk", json={"vitals": payload}).status_code == 422

    def test_missing_vitals_object_is_rejected(self, client) -> None:
        assert client.post("/sepsis-risk", json={}).status_code == 422

    def test_inference_is_logged(self, client, isolated_log) -> None:
        client.post("/sepsis-risk", json={"vitals": SEPTIC})
        summary = isolated_log.per_model_summary()
        assert any(row["model_key"] == "sepsis_heuristic" for row in summary)


@pytest.mark.heavy
class TestTrainedModel:
    def test_serves_xgboost_with_shap_when_present(self, client) -> None:
        if not sepsis_service._model.warm():
            pytest.skip("sepsis_model.pkl and/or xgboost+shap are not installed")

        body = client.post("/sepsis-risk", json={"vitals": SEPTIC}).json()
        assert body["engine"] == "xgboost"
        assert body["explanation_method"] == "shap"
        assert body["degraded"] is False
