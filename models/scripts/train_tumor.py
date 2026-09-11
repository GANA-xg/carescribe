"""FB-05 — train the brain-tumour MRI classifier.

    python scripts/download_data.py
    python scripts/train_tumor.py --epochs 8

Runs standalone on CPU or GPU. The checkpoint it writes is exactly what
``services/tumor_service.py`` loads, including the class order, so the two can
never disagree about which output index means "glioma".

CPU training on the full 7,200-image set takes hours; use ``--epochs 1
--limit-per-class`` for a smoke test that still produces a loadable checkpoint.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from architectures import CLASSES, DEFAULT_IMAGE_SIZE, build_tumor_model  # noqa: E402
from brain_tumor_data import (  # noqa: E402
    build_datasets,
    build_loaders,
    dataset_classes,
    describe,
    resolve_splits,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=SERVICE_ROOT / "data" / "brain_tumor",
        help="Dataset root containing Training/ and Testing/",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SERVICE_ROOT / "weights" / "tumor_model.pth",
        help="Checkpoint path the model service reads",
    )
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=DEFAULT_IMAGE_SIZE)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--limit-per-class",
        type=int,
        default=0,
        help="Cap images per class (0 = use everything); useful for smoke tests",
    )
    parser.add_argument(
        "--freeze-backbone",
        action="store_true",
        help="Train the head only; much faster, lower ceiling",
    )
    parser.add_argument("--no-pretrained", action="store_true",
                        help="Skip ImageNet weights (no network required)")
    return parser.parse_args(argv)


def limit_dataset(dataset, per_class: int):
    """Deterministically cap a dataset to ``per_class`` images per label."""
    if per_class <= 0:
        return dataset
    from torch.utils.data import Subset

    seen: dict[int, int] = {}
    keep: list[int] = []
    for index, (_, label) in enumerate(dataset.samples):
        if seen.get(label, 0) < per_class:
            keep.append(index)
            seen[label] = seen.get(label, 0) + 1
    return Subset(dataset, keep)


def evaluate(model, loader, device, *, criterion) -> tuple[float, float]:
    """Return ``(mean_loss, accuracy)`` over a loader."""
    import torch

    model.eval()
    total_loss, correct, total = 0.0, 0, 0
    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            total_loss += float(criterion(logits, labels)) * labels.size(0)
            correct += int((logits.argmax(dim=1) == labels).sum())
            total += labels.size(0)
    if total == 0:
        return 0.0, 0.0
    return total_loss / total, correct / total


def train(args: argparse.Namespace) -> int:
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        print(
            "PyTorch is not installed. Install the CPU wheels:\n"
            "  pip install torch torchvision --index-url "
            "https://download.pytorch.org/whl/cpu",
            file=sys.stderr,
        )
        return 2

    from config import get_settings
    from utils.timing import now_iso

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    splits = resolve_splits(args.data_dir)
    train_dataset, val_dataset = build_datasets(splits, image_size=args.image_size)
    train_dataset = limit_dataset(train_dataset, args.limit_per_class)
    val_dataset = limit_dataset(val_dataset, args.limit_per_class)

    classes = dataset_classes(train_dataset) or list(CLASSES)
    print(f"Classes (this order is saved in the checkpoint): {classes}")
    if set(classes) != set(CLASSES):
        print(
            f"Warning: dataset labels {sorted(classes)} differ from the documented "
            f"set {sorted(CLASSES)}.",
            file=sys.stderr,
        )
    print(f"Train: {describe(train_dataset)}")
    print(f"Val:   {describe(val_dataset)}")

    train_loader, val_loader = build_loaders(
        train_dataset, val_dataset, batch_size=args.batch_size, workers=args.workers
    )

    device = torch.device(get_settings().device)
    print(f"Device: {device}")

    model = build_tumor_model(num_classes=len(classes), pretrained=not args.no_pretrained)
    if args.freeze_backbone:
        for parameter in model.features.parameters():
            parameter.requires_grad = False
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    trainable = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))

    best_accuracy, best_epoch, best_state = -1.0, 0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        started = time.perf_counter()
        running_loss, seen = 0.0, 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()

            running_loss += float(loss) * labels.size(0)
            seen += labels.size(0)

        scheduler.step()
        train_loss = running_loss / seen if seen else 0.0
        val_loss, val_accuracy = evaluate(model, val_loader, device, criterion=criterion)
        elapsed = time.perf_counter() - started

        print(
            f"epoch {epoch}/{args.epochs}  train_loss={train_loss:.4f}  "
            f"val_loss={val_loss:.4f}  val_acc={val_accuracy:.4f}  ({elapsed:.1f}s)"
        )

        if val_accuracy > best_accuracy:
            best_accuracy, best_epoch = val_accuracy, epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

    if best_state is None:
        print("Training produced no checkpoint; did the loaders yield any batches?", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": best_state,
            "arch": "efficientnet_b0",
            "classes": classes,
            "image_size": args.image_size,
            "epochs": args.epochs,
            "best_epoch": best_epoch,
            "val_accuracy": round(best_accuracy, 4),
            "trained_at": now_iso(),
            "torch_version": torch.__version__,
            "seed": args.seed,
            "data_dir": str(args.data_dir),
            "freeze_backbone": bool(args.freeze_backbone),
            "limit_per_class": args.limit_per_class,
            "train_size": len(train_dataset),
            "val_size": len(val_dataset),
        },
        str(args.out),
    )

    print(f"\nSaved checkpoint to {args.out}")
    print(f"Best validation accuracy: {best_accuracy:.4f} (epoch {best_epoch})")
    print(f"Manifest: {json.dumps({'classes': classes, 'image_size': args.image_size})}")
    return 0


def main() -> int:
    return train(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
