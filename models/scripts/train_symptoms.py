"""FB-06 — train the symptom-to-condition classifier.

    python scripts/train_symptoms.py --csv data/symptoms.csv

Produces the bundle ``services/symptoms_service.py`` loads:
``{mlb, model, conditions, threshold, ...}``.

Three CSV layouts are auto-detected, because the public symptom datasets use all
of them:

* **wide**  — a condition column plus ``Symptom_1 .. Symptom_N`` columns;
* **packed** — a condition column plus one delimited symptom column
  (``"itching; skin_rash; nodal_skin_eruptions"``);
* **long**  — a condition column plus one symptom per row.

Parsing uses the standard library, so no pandas or ``datasets`` install is
needed. A HuggingFace dataset can be pulled with ``--hf-dataset`` if the optional
``datasets`` package is present.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

#: Column names that hold the label, in preference order.
CONDITION_KEYS = ("disease", "condition", "diagnosis", "prognosis", "label", "target")
#: Column names that hold a symptom list, in preference order.
SYMPTOM_KEYS = ("symptoms", "symptom", "symptom_list")
#: Delimiters seen in packed symptom columns.
DELIMITERS = (";", ",", "|", ":")

#: Symmetric threshold for "yes" when a wide table uses binary flags.
POSITIVE_TOKENS = {"1", "yes", "y", "true", "present", "t"}


def sniff_delimiter(value: str) -> str:
    """Pick the delimiter that splits ``value`` into the most parts."""
    best, best_count = ";", 1
    for candidate in DELIMITERS:
        count = value.count(candidate)
        if count > best_count:
            best, best_count = candidate, count
    return best


def pick_column(fieldnames: list[str], keys: tuple[str, ...]) -> str | None:
    lowered = {name.lower().strip(): name for name in fieldnames}
    for key in keys:
        if key in lowered:
            return lowered[key]
    # Fall back to a prefix match, e.g. "Symptom_1" style headers.
    for name in fieldnames:
        for key in keys:
            if name.lower().strip().startswith(key):
                return name
    return None


def parse_rows(path: Path) -> list[tuple[str, list[str]]]:
    """Read a CSV into ``(condition, [symptoms])`` pairs."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        if not fieldnames:
            raise ValueError(f"{path} has no header row")

        condition_column = pick_column(fieldnames, CONDITION_KEYS)
        if condition_column is None:
            raise ValueError(
                f"{path}: no condition column found. Expected one of {CONDITION_KEYS}; "
                f"got {fieldnames}"
            )

        symptom_columns = [
            name for name in fieldnames if name != condition_column
            and "symptom" in name.lower()
        ]
        packed_column = pick_column(
            [name for name in fieldnames if name != condition_column], SYMPTOM_KEYS
        )

        records: list[tuple[str, list[str]]] = []
        for row in reader:
            condition = (row.get(condition_column) or "").strip()
            if not condition:
                continue
            collected: list[str] = []

            if symptom_columns:
                # Wide layout: keep only truthy flags when the cells look binary,
                # otherwise treat each populated cell as a symptom name.
                values = [(row.get(name) or "").strip() for name in symptom_columns]
                binary = all(
                    value == "" or value.lower() in POSITIVE_TOKENS for value in values
                )
                for name, value in zip(symptom_columns, values):
                    if not value:
                        continue
                    if binary:
                        if value.lower() in POSITIVE_TOKENS:
                            collected.append(name)
                    else:
                        collected.append(value)
            elif packed_column:
                packed = (row.get(packed_column) or "").strip()
                if packed:
                    collected.extend(
                        part.strip() for part in packed.split(sniff_delimiter(packed))
                    )
            else:
                raise ValueError(
                    f"{path}: no symptom column found. Expected a 'symptom*' column; "
                    f"got {fieldnames}"
                )

            collected = [item.replace("_", " ").strip().lower() for item in collected if item.strip()]
            if collected:
                records.append((condition, collected))

        return records


def load_hf_dataset(dataset_id: str, split: str) -> list[tuple[str, list[str]]]:
    """Pull a HuggingFace dataset and convert it to the same record shape."""
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError as exc:
        raise SystemExit(
            "the optional `datasets` package is required for --hf-dataset:\n"
            "  pip install datasets"
        ) from exc

    rows = load_dataset(dataset_id, split=split)
    if not rows:
        raise SystemExit(f"{dataset_id}[{split}] is empty")

    fieldnames = list(rows.features.keys())
    condition_column = pick_column(fieldnames, CONDITION_KEYS)
    if condition_column is None:
        raise SystemExit(
            f"{dataset_id}: no condition column found among {fieldnames}"
        )
    symptom_columns = [
        name for name in fieldnames if name != condition_column and "symptom" in name.lower()
    ]

    records: list[tuple[str, list[str]]] = []
    for row in rows:
        condition = str(row.get(condition_column) or "").strip()
        collected = [
            str(row.get(name) or "").replace("_", " ").strip().lower()
            for name in symptom_columns
        ]
        collected = [item for item in collected if item and item not in {"nan", "none"}]
        if condition and collected:
            records.append((condition, collected))
    return records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", type=Path, help="Training CSV")
    source.add_argument("--hf-dataset", help="HuggingFace dataset id")
    parser.add_argument("--hf-split", default="train")
    parser.add_argument(
        "--out",
        type=Path,
        default=SERVICE_ROOT / "weights" / "symptom_model.pkl",
        help="Bundle path the model service reads",
    )
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--trees", type=int, default=300)
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.30,
        help="Minimum probability before the service reports a condition",
    )
    return parser.parse_args(argv)


def train(args: argparse.Namespace) -> int:
    try:
        import joblib
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, classification_report
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import MultiLabelBinarizer
    except ImportError:
        print("scikit-learn and joblib are required: pip install scikit-learn joblib", file=sys.stderr)
        return 2

    from utils.timing import now_iso

    if args.csv:
        records = parse_rows(args.csv)
        source = str(args.csv)
    else:
        records = load_hf_dataset(args.hf_dataset, args.hf_split)
        source = f"{args.hf_dataset}[{args.hf_split}]"

    if len(records) < 20:
        print(
            f"Only {len(records)} usable rows from {source}; refusing to train on that.",
            file=sys.stderr,
        )
        return 1

    conditions = sorted({condition for condition, _ in records})
    symptom_sets = [symptoms for _, symptoms in records]
    labels = [condition for condition, _ in records]
    vocabulary = sorted({symptom for symptoms in symptom_sets for symptom in symptoms})

    print(f"Source:      {source}")
    print(f"Rows:        {len(records)}")
    print(f"Conditions:  {len(conditions)}")
    print(f"Symptoms:    {len(vocabulary)}")

    multihot = MultiLabelBinarizer(classes=vocabulary)
    features = multihot.fit_transform(symptom_sets)

    train_x, test_x, train_y, test_y = train_test_split(
        features, labels, test_size=args.test_size, random_state=args.seed, stratify=labels
    )

    classifier = RandomForestClassifier(
        n_estimators=args.trees,
        random_state=args.seed,
        class_weight="balanced",
        n_jobs=-1,
    )
    classifier.fit(train_x, train_y)

    predictions = classifier.predict(test_x)
    accuracy = float(accuracy_score(test_y, predictions))
    print(f"\nHeld-out accuracy: {accuracy:.4f}\n")
    print(
        classification_report(
            test_y,
            predictions,
            labels=sorted(set(test_y)),
            zero_division=0,
        )
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "mlb": multihot,
            "model": classifier,
            "conditions": conditions,
            "threshold": args.threshold,
            "trained_at": now_iso(),
            "source": source,
            "n_train": int(train_x.shape[0]),
            "n_test": int(test_x.shape[0]),
            "accuracy": round(accuracy, 4),
            "seed": args.seed,
        },
        args.out,
    )
    print(f"Saved bundle to {args.out}")
    print(
        "Manifest: "
        + json.dumps(
            {"conditions": len(conditions), "symptoms": len(vocabulary), "accuracy": round(accuracy, 4)}
        )
    )
    return 0


def main() -> int:
    return train(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
