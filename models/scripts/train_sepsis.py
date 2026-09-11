"""FB-07 — train the sepsis-onset classifier.

    python scripts/train_sepsis.py --csv data/sepsis.csv
    python scripts/train_sepsis.py --synthetic 8000      # smoke test only

Features: temperature, heart rate, respiratory rate, WBC, lactate. Label: sepsis
onset within 6 hours.

**On the data.** MIMIC-III and eICU both require credentialed access and a
signed data-use agreement, so no script can download them unattended. ``--csv``
expects the five features plus a label column, which is what the eICU/MIMIC
extraction queries in ``docs/`` produce. Use ``--synthetic`` only to smoke-test
the pipeline: it samples separable distributions, so its accuracy is meaningless
and must never be quoted in the paper. The saved bundle records which path
produced it, and the script prints a warning for synthetic runs.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from services.sepsis_service import FEATURES  # noqa: E402

#: Accepted label column names.
LABEL_KEYS = ("sepsis", "sepsis_label", "label", "target", "onset", "outcome")

#: Canonical feature name -> accepted CSV header spellings.
FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "temp": ("temp", "temperature", "temperature_c", "temp_c"),
    "hr": ("hr", "heart_rate", "heartrate", "pulse"),
    "rr": ("rr", "resp_rate", "respiratory_rate", "resprate"),
    "wbc": ("wbc", "white_blood_cells", "wbc_count", "leucocytes"),
    "lactate": ("lactate", "lactate_mmol", "serum_lactate"),
}

#: Plausible ranges for adult vitals; rows outside them are dropped as corrupt.
PLAUSIBLE: dict[str, tuple[float, float]] = {
    "temp": (25.0, 45.0),
    "hr": (20.0, 300.0),
    "rr": (4.0, 80.0),
    "wbc": (0.1, 100.0),
    "lactate": (0.1, 40.0),
}


def pick(header: list[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {name.lower().strip(): name for name in header}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    return None


def load_csv(path: Path) -> tuple[list[list[float]], list[int]]:
    """Read features and labels, dropping rows that fail plausibility checks."""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        if not header:
            raise ValueError(f"{path} has no header row")

        columns = {}
        for feature, aliases in FEATURE_ALIASES.items():
            column = pick(header, aliases)
            if column is None:
                raise ValueError(
                    f"{path}: could not find a column for '{feature}'. "
                    f"Accepted names: {aliases}. Header was {header}"
                )
            columns[feature] = column

        label_column = pick(header, LABEL_KEYS)
        if label_column is None:
            raise ValueError(
                f"{path}: could not find a label column. Accepted names: {LABEL_KEYS}"
            )

        features: list[list[float]] = []
        labels: list[int] = []
        dropped = 0

        for row in reader:
            try:
                values = [float(row[columns[name]]) for name in FEATURES]
                label = int(float(row[label_column]))
            except (TypeError, ValueError):
                dropped += 1
                continue
            if label not in (0, 1):
                dropped += 1
                continue
            if any(
                not (low <= value <= high)
                for (low, high), value in zip(
                    (PLAUSIBLE[name] for name in FEATURES), values
                )
            ):
                dropped += 1
                continue
            features.append(values)
            labels.append(label)

    if dropped:
        print(f"Dropped {dropped} unusable rows.")
    return features, labels


def synthesise(count: int, seed: int) -> tuple[list[list[float]], list[int]]:
    """Generate separable demo data. **Not clinically meaningful.**

    Sepsis cases are drawn from a distribution with higher temperature, heart
    rate, respiratory rate, WBC and lactate than controls. Real cohorts overlap
    far more than this, which is exactly why a model trained here must not be
    reported.
    """
    import numpy as np

    rng = np.random.default_rng(seed)
    half = max(1, count // 2)

    healthy = np.column_stack(
        [
            rng.normal(37.0, 0.4, half),      # temp
            rng.normal(80.0, 10.0, half),     # hr
            rng.normal(16.0, 2.0, half),      # rr
            rng.normal(8.0, 2.0, half),       # wbc
            rng.normal(1.2, 0.4, half),       # lactate
        ]
    )
    septic = np.column_stack(
        [
            rng.normal(38.6, 0.9, half),
            rng.normal(118.0, 16.0, half),
            rng.normal(27.0, 5.0, half),
            rng.normal(16.5, 4.5, half),
            rng.normal(3.8, 1.4, half),
        ]
    )

    features = [
        [float(value) for value in row]
        for row in np.vstack([healthy, septic])
    ]
    labels = [0] * half + [1] * half
    return features, labels


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--csv", type=Path, help="Extracted MIMIC/eICU CSV")
    source.add_argument("--synthetic", type=int, help="Row count for demo data (paper: do not use)")
    parser.add_argument(
        "--out",
        type=Path,
        default=SERVICE_ROOT / "weights" / "sepsis_model.pkl",
        help="Bundle path the model service reads",
    )
    parser.add_argument("--test-size", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--estimators", type=int, default=400)
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    return parser.parse_args(argv)


def train(args: argparse.Namespace) -> int:
    try:
        import joblib
        import numpy as np
        import shap
        import xgboost
        from sklearn.metrics import classification_report, roc_auc_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        print(
            f"Missing training dependency: {exc}\n"
            "  pip install -r requirements-models.txt",
            file=sys.stderr,
        )
        return 2

    from utils.timing import now_iso

    if args.csv:
        features, labels = load_csv(args.csv)
        source, synthetic = str(args.csv), False
    else:
        features, labels = synthesise(args.synthetic, args.seed)
        source, synthetic = f"synthetic:{args.synthetic}", True

    if len(labels) < 50:
        print(f"Refusing to train on {len(labels)} rows.", file=sys.stderr)
        return 1
    if len(set(labels)) < 2:
        print("Labels are single-class; nothing to learn.", file=sys.stderr)
        return 1

    matrix = np.asarray(features, dtype=np.float32)
    target = np.asarray(labels, dtype=np.int32)

    if synthetic:
        print(
            "\n*** WARNING: training on SYNTHETIC data. The resulting model's accuracy\n"
            "*** is an artefact of the generator and must never be reported.\n"
        )

    positives = int(target.sum())
    print(f"Source:      {source}")
    print(f"Rows:        {len(target)} ({positives} positive, {len(target) - positives} negative)")
    print(f"Positives:   {positives / len(target):.3%}")

    train_x, test_x, train_y, test_y = train_test_split(
        matrix, target, test_size=args.test_size, random_state=args.seed, stratify=target
    )

    # scale_pos_weight counters the class imbalance typical of sepsis cohorts.
    imbalance = float((train_y == 0).sum()) / max(1.0, float((train_y == 1).sum()))
    classifier = xgboost.XGBClassifier(
        n_estimators=args.estimators,
        max_depth=args.max_depth,
        learning_rate=args.learning_rate,
        subsample=0.9,
        colsample_bytree=0.9,
        scale_pos_weight=imbalance,
        eval_metric="logloss",
        random_state=args.seed,
    )
    classifier.fit(train_x, train_y)

    probabilities = classifier.predict_proba(test_x)[:, 1]
    predictions = (probabilities >= 0.5).astype(int)
    auc = float(roc_auc_score(test_y, probabilities))

    print(f"\nHeld-out ROC AUC: {auc:.4f}\n")
    print(classification_report(test_y, predictions, digits=3, zero_division=0))

    explainer = shap.TreeExplainer(classifier)
    try:
        import numpy as _np  # noqa: F401

        sample = test_x[: min(200, len(test_x))]
        mean_abs = _np.abs(_np.asarray(explainer.shap_values(sample))).mean(axis=0)
        importances = sorted(
            zip(FEATURES, (float(value) for value in _np.ravel(mean_abs))),
            key=lambda pair: -pair[1],
        )
        print("Mean |SHAP| per feature:")
        for name, value in importances:
            print(f"  {name:<8} {value:.4f}")
    except Exception as exc:  # noqa: BLE001 - reporting only
        print(f"(feature attribution summary unavailable: {exc})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": classifier,
            "features": list(FEATURES),
            "threshold": 0.5,
            "trained_at": now_iso(),
            "source": source,
            "synthetic": synthetic,
            "roc_auc": round(auc, 4),
            "n_train": int(len(train_y)),
            "n_test": int(len(test_y)),
            "prevalence": round(positives / len(target), 4),
            "seed": args.seed,
            "xgboost_version": xgboost.__version__,
        },
        args.out,
    )
    print(f"\nSaved bundle to {args.out}")
    print(json.dumps({"roc_auc": round(auc, 4), "synthetic": synthetic, "n": len(target)}))
    return 0


def main() -> int:
    return train(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
