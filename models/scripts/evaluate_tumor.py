"""FB-11 — tumour classifier evaluation.

    python scripts/evaluate_tumor.py --data-dir data/brain_tumor --out reports

Reports, on the held-out test split:

* overall accuracy;
* per-class precision, recall and F1;
* the full confusion matrix (as a markdown table and as a CSV);
* macro one-vs-rest ROC AUC, which is the number to compare against the
  published baseline rather than raw accuracy.

The checkpoint supplies its own class order, so this script evaluates against
exactly the labels the model was trained on rather than assuming an order.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from architectures import DEFAULT_IMAGE_SIZE  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=SERVICE_ROOT / "data" / "brain_tumor")
    parser.add_argument("--weights", type=Path,
                        default=SERVICE_ROOT / "weights" / "tumor_model.pth")
    parser.add_argument("--out", type=Path, default=SERVICE_ROOT / "reports")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--limit-per-class", type=int, default=0,
                        help="Cap images per class (0 = all); for a quick check")
    return parser.parse_args(argv)


def evaluate(args: argparse.Namespace) -> int:
    try:
        import numpy as np
        import torch
        from sklearn.metrics import (
            accuracy_score,
            classification_report,
            confusion_matrix,
            precision_recall_fscore_support,
            roc_auc_score,
        )
        from torch.utils.data import DataLoader
    except ImportError as exc:
        print(
            f"Missing dependency: {exc}\n"
            "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu\n"
            "  pip install -r requirements-models.txt",
            file=sys.stderr,
        )
        return 2

    from architectures import build_tumor_model, tumor_transform
    from brain_tumor_data import limit_dataset, resolve_splits
    from torchvision.datasets import ImageFolder

    from config import get_settings

    if not args.weights.exists():
        print(
            f"Checkpoint not found: {args.weights}\n"
            "Train one first: python scripts/train_tumor.py",
            file=sys.stderr,
        )
        return 1

    payload = torch.load(str(args.weights), map_location="cpu")
    state_dict = payload.get("state_dict", payload) if isinstance(payload, dict) else payload
    classes = list(payload.get("classes", [])) if isinstance(payload, dict) else []
    image_size = int(payload.get("image_size", DEFAULT_IMAGE_SIZE)) if isinstance(payload, dict) else DEFAULT_IMAGE_SIZE
    if not classes:
        print("Checkpoint has no class list; re-run scripts/train_tumor.py", file=sys.stderr)
        return 1

    splits = resolve_splits(args.data_dir)
    test_dataset = ImageFolder(str(splits.val), transform=tumor_transform(image_size, train=False))
    if list(test_dataset.classes) != classes:
        print(
            f"Class mismatch: checkpoint {classes} vs dataset {list(test_dataset.classes)}.\n"
            "Refusing to report metrics that would silently mislabel every confusion.",
            file=sys.stderr,
        )
        return 1
    test_dataset = limit_dataset(test_dataset, args.limit_per_class)

    device = torch.device(get_settings().device)
    model = build_tumor_model(num_classes=len(classes), pretrained=False)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()

    loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False,
                        num_workers=args.workers)

    all_labels: list[int] = []
    all_predictions: list[int] = []
    all_probabilities: list[list[float]] = []

    with torch.no_grad():
        for images, labels in loader:
            logits = model(images.to(device))
            probabilities = torch.softmax(logits, dim=-1).cpu().numpy()
            all_probabilities.extend(probabilities.tolist())
            all_predictions.extend(probabilities.argmax(axis=1).tolist())
            all_labels.extend(labels.tolist())

    if not all_labels:
        print("Test split yielded no images.", file=sys.stderr)
        return 1

    labels_array = np.asarray(all_labels)
    predictions_array = np.asarray(all_predictions)
    probabilities_array = np.asarray(all_probabilities)

    accuracy = float(accuracy_score(labels_array, predictions_array))
    precision, recall, f1, support = precision_recall_fscore_support(
        labels_array, predictions_array, labels=list(range(len(classes))), zero_division=0
    )
    matrix = confusion_matrix(labels_array, predictions_array, labels=list(range(len(classes))))

    macro_auc = None
    try:
        if len(set(all_labels)) == len(classes) and len(classes) > 2:
            macro_auc = float(
                roc_auc_score(labels_array, probabilities_array, multi_class="ovr", average="macro")
            )
    except ValueError:
        macro_auc = None

    print(f"Checkpoint:  {args.weights}")
    print(f"Classes:     {classes}")
    print(f"Images:      {len(all_labels)}")
    print(f"Accuracy:    {accuracy:.4f}")
    if macro_auc is not None:
        print(f"Macro AUC:   {macro_auc:.4f}")
    print()
    print(classification_report(labels_array, predictions_array, labels=list(range(len(classes))),
                                target_names=classes, digits=4, zero_division=0))

    write_reports(
        args.out,
        classes=classes,
        accuracy=accuracy,
        macro_auc=macro_auc,
        precision=precision,
        recall=recall,
        f1=f1,
        support=support,
        matrix=matrix,
        n_images=len(all_labels),
        checkpoint=args.weights,
    )
    return 0


def write_reports(
    out_dir: Path,
    *,
    classes: list[str],
    accuracy: float,
    macro_auc: float | None,
    precision,
    recall,
    f1,
    support,
    matrix,
    n_images: int,
    checkpoint: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [
        {
            "class": name,
            "precision": round(float(precision[index]), 4),
            "recall": round(float(recall[index]), 4),
            "f1": round(float(f1[index]), 4),
            "support": int(support[index]),
        }
        for index, name in enumerate(classes)
    ]
    csv_path = out_dir / "tumor_evaluation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["class", "precision", "recall", "f1", "support"])
        writer.writeheader()
        writer.writerows(rows)

    matrix_path = out_dir / "tumor_confusion_matrix.csv"
    with matrix_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["actual \\ predicted", *classes])
        for index, name in enumerate(classes):
            writer.writerow([name, *[int(value) for value in matrix[index]]])

    lines = [
        "# Tumour classifier evaluation",
        "",
        f"- Checkpoint: `{checkpoint}`",
        f"- Held-out images: **{n_images}**",
        f"- Overall accuracy: **{accuracy:.4f}**",
    ]
    if macro_auc is not None:
        lines.append(f"- Macro one-vs-rest ROC AUC: **{macro_auc:.4f}**")
    lines += [
        "",
        "## Per-class metrics",
        "",
        "| Class | Precision | Recall | F1 | Support |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['class']} | {row['precision']:.4f} | {row['recall']:.4f} | "
            f"{row['f1']:.4f} | {row['support']} |"
        )

    lines += ["", "## Confusion matrix", "", "| Actual \\ Predicted | " + " | ".join(classes) + " |",
              "| --- | " + " | ".join("---" for _ in classes) + " |"]
    for index, name in enumerate(classes):
        lines.append(f"| **{name}** | " + " | ".join(str(int(v)) for v in matrix[index]) + " |")

    lines += [
        "",
        "## Caveats for the paper",
        "",
        "The Kaggle dataset's Training/Testing split is **slice-level**, not",
        "patient-level: consecutive slices from one scan can appear in both splits,",
        "which inflates accuracy relative to true generalisation to unseen patients.",
        "State this explicitly when reporting these numbers, and prefer the macro AUC",
        "over raw accuracy when comparing against published baselines.",
    ]

    markdown_path = out_dir / "tumor_evaluation.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {markdown_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {matrix_path}")


def main() -> int:
    return evaluate(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
