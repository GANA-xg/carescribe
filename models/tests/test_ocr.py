"""FB-02 tests — the ``/ocr`` contract and the merge strategy.

The merge is pure, so it is tested directly with synthetic engine outputs. That
covers the interesting logic without needing multi-GB weights on the test box.
"""

from __future__ import annotations

import pytest

from services.ocr_service import OcrService

DONUT_TRANSCRIPT = (
    "Dr A Sharma\n"
    "<s_drug>Dolo 650 mg</s_drug> <s_drug>Augmentin 625 mg</s_drug>\n"
    "<s_diagnosis>Acute pharyngitis</s_diagnosis>\n"
    "Date: 14/08/2026\n"
)

CHANDRA_MARKDOWN = (
    "Dr A Sharma\n"
    "1. Dolo 650 mg  1-0-1\n"
    "2. Augmentin 625 mg  BD\n"
    "Diagnosis: Acute pharyngitis\n"
    "Date: 14/08/2026\n"
)


def engine(*, text: str = "", confidence: float = 0.0, **extra) -> dict:
    """Build a fake engine output in the shape the merge step expects."""
    return {"text": text, "confidence": confidence, **extra}


class TestMerge:
    def test_both_engines_produce_a_merged_result(self) -> None:
        donut = engine(
            text=DONUT_TRANSCRIPT,
            confidence=0.8,
            fields={"drug": ["Dolo 650 mg", "Augmentin 625 mg"], "diagnosis": ["Acute pharyngitis"]},
        )
        chandra = engine(text=CHANDRA_MARKDOWN, confidence=0.7, markdown=CHANDRA_MARKDOWN)

        merged, agreement, extraction = OcrService.merge(donut=donut, chandra=chandra)

        assert merged["engine"] == "chandra+donut"
        assert merged["structured"]["diagnosis"] == "Acute pharyngitis"
        assert merged["structured"]["date"] == "14/08/2026"
        assert "dolo" in [drug.lower() for drug in merged["structured"]["drugs"]]
        assert "augmentin" in [drug.lower() for drug in merged["structured"]["drugs"]]
        assert 0.0 <= agreement <= 1.0
        assert extraction == 1.0

    def test_chandra_markdown_is_the_primary_transcript(self) -> None:
        # Chandra preserves layout, so its text wins when both are present.
        donut = engine(text="Dolo 650\nAugmentin 625\nAcute pharyngitis")
        chandra = engine(text=CHANDRA_MARKDOWN, markdown=CHANDRA_MARKDOWN)

        merged, _, _ = OcrService.merge(donut=donut, chandra=chandra)
        assert merged["text"] == CHANDRA_MARKDOWN

    def test_longer_donut_transcript_wins_when_chandra_is_terse(self) -> None:
        donut = engine(text=DONUT_TRANSCRIPT)
        chandra = engine(text="Prescription.", markdown="Prescription.")

        merged, _, _ = OcrService.merge(donut=donut, chandra=chandra)
        assert merged["text"] == DONUT_TRANSCRIPT

    def test_agreement_is_one_for_identical_engines(self) -> None:
        payload = engine(text=CHANDRA_MARKDOWN)
        _, agreement, _ = OcrService.merge(donut=dict(payload), chandra=dict(payload))
        assert agreement == 1.0

    def test_disagreeing_engines_score_lower_than_agreeing_ones(self) -> None:
        same = engine(text="Dolo 650 mg BD")
        _, identical, _ = OcrService.merge(donut=dict(same), chandra=dict(same))

        _, divergent, _ = OcrService.merge(
            donut=engine(text="Dolo 650 mg BD"),
            chandra=engine(text="Totally different content entirely"),
        )
        assert divergent < identical

    def test_only_donut_available(self) -> None:
        merged, agreement, _ = OcrService.merge(
            donut=engine(text=DONUT_TRANSCRIPT, confidence=0.9), chandra=engine()
        )
        assert merged["engine"] == "donut"
        assert merged["text"] == DONUT_TRANSCRIPT
        assert agreement == 0.0

    def test_only_chandra_available(self) -> None:
        merged, _, _ = OcrService.merge(
            donut=engine(), chandra=engine(text=CHANDRA_MARKDOWN, markdown=CHANDRA_MARKDOWN)
        )
        assert merged["engine"] == "chandra"
        assert merged["text"] == CHANDRA_MARKDOWN

    def test_no_engines_available_yields_an_empty_merged_result(self) -> None:
        merged, agreement, extraction = OcrService.merge(donut=engine(), chandra=engine())
        assert merged["engine"] == "none"
        assert merged["text"] == ""
        assert merged["structured"]["drugs"] == []
        assert agreement == 0.0
        assert extraction == 0.0

    def test_drugs_from_both_sources_are_unioned_without_duplicates(self) -> None:
        donut = engine(
            text=DONUT_TRANSCRIPT,
            fields={"drug": ["Dolo 650 mg", "dolo 650 mg", "Zylofast 250 mg"]},
        )
        merged, _, _ = OcrService.merge(donut=donut, chandra=engine(text=CHANDRA_MARKDOWN))

        drugs = [drug.lower() for drug in merged["structured"]["drugs"]]
        assert len(drugs) == len(set(drugs))
        assert "zylofast 250 mg" in drugs


class TestParseDonutTags:
    def test_tagged_fields_are_extracted(self) -> None:
        fields = OcrService._parse_donut_tags(
            "<s_drug>Dolo 650</s_drug><s_drug>Azee 500</s_drug><s_diagnosis>URTI</s_diagnosis>"
        )
        assert fields["drug"] == ["Dolo 650", "Azee 500"]
        assert fields["diagnosis"] == ["URTI"]

    def test_untagged_text_yields_no_fields(self) -> None:
        assert OcrService._parse_donut_tags("plain transcript") == {}


class TestOcrEndpoint:
    def test_returns_both_engines_and_the_merge(self, client, png_b64) -> None:
        response = client.post("/ocr", json={"image_b64": png_b64})
        assert response.status_code == 200
        body = response.json()

        # Contract: both engines separately, plus the merged result.
        assert set(body["donut"]) >= {"text", "confidence"}
        assert set(body["chandra"]) >= {"text", "markdown", "confidence"}
        assert "structured" in body["merged"]
        assert set(body["merged"]["structured"]) == {"drugs", "diagnosis", "date"}
        assert 0.0 <= body["agreement"] <= 1.0

    def test_reports_version_and_per_engine_timings(self, client, png_b64) -> None:
        body = client.post("/ocr", json={"image_b64": png_b64}).json()
        assert body["model_version"]
        assert body["inference_time_ms"] >= 0.0
        assert set(body["timings"]) == {"donut", "chandra", "merge"}

    def test_marks_engines_unavailable_and_degrades_without_weights(self, client, png_b64) -> None:
        body = client.post("/ocr", json={"image_b64": png_b64}).json()
        assert body["degraded"] is True
        assert body["engines"] == {"donut": "unavailable", "chandra": "unavailable"}
        # Nothing is fabricated when no engine can read the page.
        assert body["donut"]["text"] == ""
        assert body["chandra"]["text"] == ""
        assert body["merged"]["text"] == ""
        assert body["agreement"] == 0.0

    def test_accepts_a_data_uri_prefix(self, client, png_b64) -> None:
        response = client.post("/ocr", json={"image_b64": f"data:image/png;base64,{png_b64}"})
        assert response.status_code == 200

    def test_rejects_a_non_image_payload(self, client) -> None:
        response = client.post("/ocr", json={"image_b64": "bm90IGFuIGltYWdl"})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"

    def test_rejects_an_empty_payload(self, client) -> None:
        assert client.post("/ocr", json={"image_b64": ""}).status_code == 422

    def test_rejects_an_image_too_small_to_read(self, client, image_factory) -> None:
        tiny = image_factory(8, 8)
        response = client.post("/ocr", json={"image_b64": tiny})
        assert response.status_code == 400
        assert response.json()["error"] == "invalid_image"

    def test_records_the_merge_in_the_inference_log(self, client, png_b64, isolated_log) -> None:
        client.post("/ocr", json={"image_b64": png_b64})
        keys = {row["model_key"] for row in isolated_log.per_model_summary()}
        assert "ocr_merge" in keys


@pytest.mark.heavy
class TestRealEngines:
    """Runs only with transformers + torch, and downloads weights on first use."""

    def test_donut_and_chandra_serve_real_transcripts(self, client, png_b64) -> None:
        from services.ocr_service import SERVICE

        if not (SERVICE._donut.warm() and SERVICE._chandra.warm()):
            pytest.skip("Donut and/or Chandra weights are not installed")

        body = client.post("/ocr", json={"image_b64": png_b64}).json()
        assert body["degraded"] is False
