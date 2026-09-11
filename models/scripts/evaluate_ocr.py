"""FB-11 — OCR evaluation protocol.

    python scripts/evaluate_ocr.py \
        --images data/ocr_test/images \
        --truth  data/ocr_test/truth \
        --out    reports

Runs both engines over a folder of prescription images and compares each against
a ground-truth text file with the same stem, then writes a markdown table and a
CSV. Reproducible by design: the same inputs and the same installed engines give
the same numbers.

Metrics per engine, per image:

* **CER** — character error rate, ``edit distance / reference length``, computed
  on canonicalised text (case, punctuation and whitespace differences are not
  counted as errors);
* **WER** — the same over whitespace-separated tokens;
* **drug accuracy** — exact-match recall of drug names;
* **latency** — milliseconds, which the paper reports alongside accuracy.

**On drug ground truth.** Ideally pass ``--truth-drugs drugs.json`` (a mapping of
image stem to a list of drug names) so accuracy is measured against human
annotation. Without it, the script derives the reference drugs from the truth
text with the lexicon parser — convenient and reproducible, but it measures
*agreement with the parser*, not absolute accuracy. The script says which was
used in the report header so a reader cannot be misled.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from utils.confidence import character_error_rate, drug_extraction_accuracy, word_error_rate  # noqa: E402
from utils.text import extract_entities  # noqa: E402

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


@dataclass
class Sample:
    stem: str
    reference: str
    reference_drugs: list[str]


@dataclass
class EngineScore:
    engine: str
    cer: float
    wer: float
    drug_accuracy: float
    latency_ms: float
    predicted_chars: int


@dataclass
class ImageResult:
    stem: str
    scores: list[EngineScore] = field(default_factory=list)
    agreement: float = 0.0
    error: str | None = None


def load_samples(images: Path, truth: Path, truth_drugs: Path | None) -> list[Sample]:
    """Pair each image with its ground-truth text (and annotated drugs)."""
    if not images.is_dir():
        raise SystemExit(f"images directory not found: {images}")
    if not truth.is_dir():
        raise SystemExit(f"truth directory not found: {truth}")

    annotations: dict[str, list[str]] = {}
    if truth_drugs is not None:
        annotations = json.loads(truth_drugs.read_text(encoding="utf-8"))

    samples: list[Sample] = []
    for image in sorted(images.iterdir()):
        if image.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        reference_path = truth / f"{image.stem}.txt"
        if not reference_path.exists():
            print(f"  skip {image.name}: no {reference_path.name}", file=sys.stderr)
            continue
        reference = reference_path.read_text(encoding="utf-8")
        drugs = annotations.get(image.stem)
        if drugs is None:
            drugs = [str(item) for item in extract_entities(reference)["drugs"]]
        samples.append(Sample(stem=image.stem, reference=reference, reference_drugs=drugs))

    if not samples:
        raise SystemExit(
            f"no image/ground-truth pairs found. Put images in {images} and matching "
            f"<stem>.txt files in {truth}."
        )
    return samples


def score_engine(
    engine: str,
    text: str,
    latency_ms: float,
    sample: Sample,
) -> EngineScore:
    return EngineScore(
        engine=engine,
        cer=round(character_error_rate(sample.reference, text), 4),
        wer=round(word_error_rate(sample.reference, text), 4),
        drug_accuracy=drug_extraction_accuracy(
            sample.reference_drugs, extract_entities(text)["drugs"]
        ),
        latency_ms=round(latency_ms, 2),
        predicted_chars=len(text or ""),
    )


def evaluate(args: argparse.Namespace) -> int:
    from services.ocr_service import SERVICE as ocr_service

    if not (ocr_service._donut.warm() or ocr_service._chandra.warm()):
        print(
            "Neither OCR engine is installed, so there is nothing to evaluate.\n"
            "Install the optional backends first:\n"
            "  pip install -r requirements-models.txt\n"
            "  pip install git+https://github.com/datalab-to/chandra.git",
            file=sys.stderr,
        )
        return 1

    annotated = args.truth_drugs is not None
    samples = load_samples(args.images, args.truth, args.truth_drugs)
    print(f"Evaluating {len(samples)} prescription(s) with: {', '.join(ocr_service.serving_keys)}")
    print(f"Drug ground truth: {'annotated JSON' if annotated else 'lexicon-derived (agreement only)'}")

    results: list[ImageResult] = []
    for sample in samples:
        image_b64 = base64.b64encode((args.images / f"{sample.stem}{_find_suffix(args.images, sample.stem)}").read_bytes()).decode("ascii")
        result = ImageResult(stem=sample.stem)

        try:
            payload = ocr_service.process(image_b64)
        except Exception as exc:  # noqa: BLE001 - record and continue the sweep
            result.error = f"{type(exc).__name__}: {exc}"
            results.append(result)
            print(f"  {sample.stem}: FAILED ({result.error})", file=sys.stderr)
            continue

        result.agreement = float(payload["agreement"])
        timings = payload.get("timings", {})

        for engine in ("donut", "chandra"):
            output = payload[engine]
            text = output.get("text") or output.get("markdown") or ""
            # An engine that is absent or returned nothing is not scored: a
            # missing prediction is not a wrong one, and averaging zeros into
            # the CER would understate the surviving engine.
            if not text:
                continue
            result.scores.append(
                score_engine(engine, text, timings.get(engine, 0.0), sample)
            )

        results.append(result)
        rendered = ", ".join(
            f"{score.engine} CER={score.cer:.3f} WER={score.wer:.3f}" for score in result.scores
        )
        print(f"  {sample.stem}: {rendered or 'no engine produced text'}")

    write_reports(results, args.out, annotated=annotated)
    return 0


def _find_suffix(images: Path, stem: str) -> str:
    for candidate in IMAGE_SUFFIXES:
        if (images / f"{stem}{candidate}").exists():
            return candidate
    raise SystemExit(f"could not re-locate image for {stem}")


def write_reports(results: list[ImageResult], out_dir: Path, *, annotated: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for result in results:
        for score in result.scores:
            rows.append(
                {
                    "image": result.stem,
                    "engine": score.engine,
                    "cer": score.cer,
                    "wer": score.wer,
                    "drug_accuracy": score.drug_accuracy,
                    "latency_ms": score.latency_ms,
                    "predicted_chars": score.predicted_chars,
                    "cross_engine_agreement": result.agreement,
                }
            )
        if result.error:
            rows.append({"image": result.stem, "engine": "ERROR", "cer": "", "wer": "",
                         "drug_accuracy": "", "latency_ms": "", "predicted_chars": "",
                         "cross_engine_agreement": ""})

    csv_path = out_dir / "ocr_evaluation.csv"
    fieldnames = ["image", "engine", "cer", "wer", "drug_accuracy", "latency_ms",
                  "predicted_chars", "cross_engine_agreement"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    by_engine: dict[str, list[EngineScore]] = {}
    for result in results:
        for score in result.scores:
            by_engine.setdefault(score.engine, []).append(score)

    lines = [
        "# OCR evaluation",
        "",
        f"- Images evaluated: **{len(results)}**",
        f"- Drug ground truth: **{'annotated JSON' if annotated else 'lexicon-derived (agreement only)'}**",
        f"- Cross-engine agreement: **{_mean([r.agreement for r in results]):.4f}** (1 - CER)",
        "",
        "## Per-engine summary",
        "",
        "| Engine | Images | Mean CER | Mean WER | Drug accuracy | Mean latency (ms) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for engine, scores in sorted(by_engine.items()):
        lines.append(
            f"| {engine} | {len(scores)} | {_mean([s.cer for s in scores]):.4f} | "
            f"{_mean([s.wer for s in scores]):.4f} | "
            f"{_mean([s.drug_accuracy for s in scores]):.4f} | "
            f"{_mean([s.latency_ms for s in scores]):.2f} |"
        )
    if not by_engine:
        lines.append("| (none) | 0 | - | - | - | - |")

    lines += [
        "",
        "## Per-image detail",
        "",
        "| Image | Engine | CER | WER | Drug accuracy | Latency (ms) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        if not result.scores:
            lines.append(f"| {result.stem} | (none) | - | - | - | {result.error or '-'} |")
            continue
        for score in result.scores:
            lines.append(
                f"| {result.stem} | {score.engine} | {score.cer:.4f} | {score.wer:.4f} | "
                f"{score.drug_accuracy:.4f} | {score.latency_ms:.2f} |"
            )

    lines += [
        "",
        "## Method",
        "",
        "CER and WER are computed on canonicalised text: case, punctuation, bracketed",
        "asides and repeated whitespace are normalised away first, so formatting",
        "differences are not counted as recognition errors. Agreement is `1 - CER`",
        "between the two engines' transcripts.",
    ]
    if not annotated:
        lines += [
            "",
            "> Drug accuracy here compares each engine against drug names extracted from",
            "> the ground-truth text by the lexicon parser, so it measures agreement with",
            "> that parser rather than absolute accuracy. Pass `--truth-drugs` with human",
            "> annotations for a number that can be quoted.",
        ]

    markdown_path = out_dir / "ocr_evaluation.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"\nWrote {markdown_path}")
    print(f"Wrote {csv_path}")


def _mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--images", type=Path, required=True, help="Folder of prescription images")
    parser.add_argument("--truth", type=Path, required=True, help="Folder of matching <stem>.txt files")
    parser.add_argument("--truth-drugs", type=Path, default=None,
                        help="Optional JSON: {stem: [drug names]} from human annotation")
    parser.add_argument("--out", type=Path, default=SERVICE_ROOT / "reports",
                        help="Directory for the markdown and CSV outputs")
    return parser.parse_args(argv)


def main() -> int:
    return evaluate(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
