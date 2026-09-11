"""FB-12 — summarise the inference log.

    python scripts/inference_report.py
    python scripts/inference_report.py --csv reports/inference_summary.csv --limit 5000

Reads the SQLite log every endpoint writes to and prints call counts, mean
latency and degradation rates per model and per endpoint. This is the source of
the latency table in the project report and the paper, so the numbers come from
real traffic rather than from a benchmark harness.

Degraded share matters as much as latency: a model answering in 5 ms while
serving a fallback looks fast and is actually not the model.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", type=Path, default=None,
                        help="Inference SQLite path (defaults to INFERENCE_DB)")
    parser.add_argument("--csv", type=Path, default=None, help="Also write the summary as CSV")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only consider the most recent N calls (0 = all)")
    parser.add_argument("--slowest", type=int, default=10,
                        help="How many slowest calls to list")
    return parser.parse_args(argv)


def fetch(
    db_path: Path, limit: int, slowest_count: int
) -> tuple[list[dict], list[dict], list[dict], int]:
    """Return ``(per_model, per_endpoint, slowest, total_calls)``."""
    if not db_path.exists():
        raise SystemExit(
            f"No inference log at {db_path}.\n"
            "It is created on the first request; run the service and exercise some "
            "endpoints first (see the README's curl smoke test)."
        )

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row

    window = ""
    parameters: tuple = ()
    if limit > 0:
        # Bound the window without assuming monotonic timestamps for ordering.
        window = "WHERE id > (SELECT MAX(id) - ? FROM inference_log)"
        parameters = (limit,)

    per_model = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT model_key,
                   model_id,
                   COUNT(*)                                   AS calls,
                   ROUND(AVG(inference_time_ms), 2)           AS avg_ms,
                   ROUND(MIN(inference_time_ms), 2)           AS min_ms,
                   ROUND(MAX(inference_time_ms), 2)           AS max_ms,
                   ROUND(AVG(confidence), 4)                  AS avg_confidence,
                   SUM(degraded)                              AS degraded_calls,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM inference_log
            {window}
            GROUP BY model_key
            ORDER BY calls DESC
            """,
            parameters,
        )
    ]
    per_endpoint = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT endpoint,
                   COUNT(*)                         AS calls,
                   ROUND(AVG(inference_time_ms), 2) AS avg_ms
            FROM inference_log
            {window}
            GROUP BY endpoint
            ORDER BY calls DESC
            """,
            parameters,
        )
    ]
    slowest = [
        dict(row)
        for row in connection.execute(
            f"""
            SELECT ts, model_key, endpoint,
                   ROUND(inference_time_ms, 2) AS ms,
                   input_size, confidence, degraded, error
            FROM inference_log
            {window}
            ORDER BY inference_time_ms DESC
            LIMIT ?
            """,
            (*parameters, max(1, slowest_count)),
        ).fetchall()
    ]
    total = int(
        connection.execute(f"SELECT COUNT(*) FROM inference_log {window}", parameters).fetchone()[0]
    )
    connection.close()
    return per_model, per_endpoint, slowest, total


def render(per_model: list[dict], per_endpoint: list[dict], slowest: list[dict], total: int,
           slowest_count: int) -> str:
    lines = [
        "# Inference report",
        "",
        f"Total inference calls: **{total}**",
        f"Models exercised: **{len(per_model)}**",
        "",
        "## Per model",
        "",
        "| Model | Version | Calls | Mean ms | Min ms | Max ms | Mean confidence | Degraded | Errors |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in per_model:
        calls = row["calls"] or 0
        degraded = row["degraded_calls"] or 0
        share = f"{degraded} ({degraded / calls:.0%})" if calls else "0"
        lines.append(
            f"| {row['model_key']} | {row['model_id'] or '-'} | {calls} | "
            f"{_fmt(row['avg_ms'])} | {_fmt(row['min_ms'])} | {_fmt(row['max_ms'])} | "
            f"{_fmt(row['avg_confidence'])} | {share} | {row['errors'] or 0} |"
        )
    if not per_model:
        lines.append("| (no calls recorded) | - | 0 | - | - | - | - | - | - |")

    lines += ["", "## Per endpoint", "", "| Endpoint | Calls | Mean ms |", "| --- | --- | --- |"]
    for row in per_endpoint:
        lines.append(f"| {row['endpoint']} | {row['calls']} | {_fmt(row['avg_ms'])} |")
    if not per_endpoint:
        lines.append("| (no calls recorded) | 0 | - |")

    lines += [
        "",
        f"## Slowest {slowest_count} calls",
        "",
        "| Timestamp | Model | Endpoint | ms | Input | Confidence | Degraded |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in slowest:
        lines.append(
            f"| {row['ts']} | {row['model_key']} | {row['endpoint']} | {_fmt(row['ms'])} | "
            f"{row['input_size'] or '-'} | {_fmt(row['confidence'])} | "
            f"{'yes' if row['degraded'] else 'no'} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "`degraded` counts calls answered by a fallback rather than the real model.",
        "A low mean latency on a degraded row reflects the fallback's speed, not the",
        "model's — quote the two together or not at all.",
    ]
    return "\n".join(lines) + "\n"


def _fmt(value: object) -> str:
    return "-" if value is None else f"{value}"


def main() -> int:
    args = parse_args()

    db_path = args.db
    if db_path is None:
        from config import get_settings

        db_path = get_settings().inference_db

    per_model, per_endpoint, slowest, total = fetch(Path(db_path), args.limit, args.slowest)
    report = render(per_model, per_endpoint, slowest, total, args.slowest)

    print(report)

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["model_key", "model_id", "calls", "avg_ms", "min_ms", "max_ms",
                             "avg_confidence", "degraded_calls", "errors"])
            for row in per_model:
                writer.writerow([row[key] for key in
                                 ("model_key", "model_id", "calls", "avg_ms", "min_ms", "max_ms",
                                  "avg_confidence", "degraded_calls", "errors")])
        print(f"Wrote {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
