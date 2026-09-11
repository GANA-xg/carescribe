"""FB-01 / FB-12 tests — the health endpoint and service banner."""

from __future__ import annotations


class TestHealthEndpoint:
    def test_returns_ok_and_the_three_required_fields(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()

        # FB-01's minimum contract.
        assert body["status"] in {"ok", "degraded"}
        assert isinstance(body["models_loaded"], list)
        assert isinstance(body["gpu"], bool)

    def test_reports_an_empty_model_list_before_anything_loads(self, fresh_client) -> None:
        """FB-01: /health must answer during startup, before models are loaded."""
        body = fresh_client.get("/health").json()
        assert body["models_loaded"] == []
        assert body["status"] == "ok"

    def test_reports_version_and_device(self, client) -> None:
        body = client.get("/health").json()
        assert body["service_version"]
        assert body["device"]
        # CPU-only is a supported configuration (rule 6).
        assert body["gpu"] is False

    def test_lists_a_model_once_it_has_served(self, fresh_client) -> None:
        fresh_client.post("/ner", json={"text": "Tab Dolo 650 mg BD"})
        body = fresh_client.get("/health").json()

        assert "ner_regex" in body["models_loaded"]
        assert "medspacy" in body["degraded_models"]

    def test_degraded_status_is_reported_when_a_fallback_serves(self, fresh_client) -> None:
        fresh_client.post("/ner", json={"text": "Tab Dolo 650 mg BD"})
        body = fresh_client.get("/health").json()

        assert body["status"] == "degraded"
        assert body["degraded_models"] == ["medspacy"]

    def test_model_detail_carries_version_and_load_time(self, fresh_client) -> None:
        fresh_client.post("/ner", json={"text": "Tab Dolo 650 mg BD"})
        models = {item["key"]: item for item in fresh_client.get("/health").json()["models"]}

        fallback = models["ner_regex"]
        assert fallback["model_id"] == "ner-regex-v1.0"
        assert fallback["status"] == "loaded"
        assert fallback["loaded_at"]
        assert fallback["serving"] is True

        primary = models["medspacy"]
        assert primary["status"] == "degraded"
        assert primary["reason"]
        assert primary["serving"] is True
        assert primary["degraded"] is True

    def test_reason_explains_why_a_model_degraded(self, fresh_client) -> None:
        fresh_client.post("/ner", json={"text": "Tab Dolo 650 mg BD"})
        models = {item["key"]: item for item in fresh_client.get("/health").json()["models"]}
        assert "heavy models disabled" in models["medspacy"]["reason"]


class TestServiceBanner:
    def test_root_describes_the_service(self, client) -> None:
        body = client.get("/").json()
        assert body["service"] == "carescribe-models"
        assert body["internal"] is True
        assert "/health" in body["endpoints"]

    def test_openapi_schema_is_served(self, client) -> None:
        assert client.get("/openapi.json").status_code == 200
