"""Dataset discovery and loaders for the brain-tumour model.

Shared by ``train_tumor.py`` and ``evaluate_tumor.py`` so training and evaluation
cannot disagree about class order, preprocessing or the validation split.

**A note on the split.** The Kaggle dataset ships a slice-level Training/Testing
split: consecutive slices of the same scan can land on both sides. That inflates
reported accuracy relative to true patient-level generalisation, so any paper
reporting these numbers must say so. This module refuses to invent its own split
because a random re-split would not fix the problem and would make results
incomparable with the published baseline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Accepted (train, validation) directory-name pairs, in preference order.
SPLIT_NAMES: tuple[tuple[str, str], ...] = (
    ("Training", "Testing"),
    ("train", "test"),
    ("train", "val"),
)


@dataclass(frozen=True)
class Splits:
    train: Path
    val: Path


def resolve_splits(data_dir: Path) -> Splits:
    """Locate the train/validation directories, or explain what is missing."""
    if not data_dir.is_dir():
        raise FileNotFoundError(
            f"{data_dir} does not exist. Run `python scripts/download_data.py` first."
        )
    for train_name, val_name in SPLIT_NAMES:
        train, val = data_dir / train_name, data_dir / val_name
        if train.is_dir() and val.is_dir():
            return Splits(train=train, val=val)

    present = sorted(child.name for child in data_dir.iterdir() if child.is_dir())
    raise FileNotFoundError(
        f"could not find a train/validation pair under {data_dir}. "
        f"Expected one of {SPLIT_NAMES}; found: {present or '(nothing)'}"
    )


def build_datasets(
    splits: Splits,
    *,
    image_size: int,
    allow_missing_classes: bool = False,
) -> tuple[Any, Any]:
    """Create ImageFolder datasets with the shared tumour transforms."""
    from torchvision.datasets import ImageFolder

    from architectures import tumor_transform

    train = ImageFolder(str(splits.train), transform=tumor_transform(image_size, train=True))
    val = ImageFolder(str(splits.val), transform=tumor_transform(image_size, train=False))

    if not allow_missing_classes:
        missing = set(train.classes) ^ set(val.classes)
        if missing:
            raise ValueError(
                f"train/validation class sets differ: {sorted(missing)}. "
                "Evaluation against a checkpoint requires identical labels."
            )
    return train, val


def build_loaders(
    train_dataset: Any,
    val_dataset: Any,
    *,
    batch_size: int,
    workers: int,
) -> tuple[Any, Any]:
    """Wrap the datasets in deterministic DataLoaders."""
    from torch.utils.data import DataLoader

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=workers,
        pin_memory=False,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=workers,
    )
    return train_loader, val_loader


def dataset_classes(dataset: Any) -> list[str]:
    """Class names behind a dataset, seeing through a ``Subset`` wrapper."""
    base = getattr(dataset, "dataset", dataset)
    return list(getattr(base, "classes", []))


def dataset_samples(dataset: Any) -> list[tuple[str, int]]:
    """``(path, label_index)`` pairs, honouring a ``Subset``'s index list."""
    base = getattr(dataset, "dataset", dataset)
    samples = list(getattr(base, "samples", []))
    indices = getattr(dataset, "indices", None)
    if indices is not None:
        samples = [samples[index] for index in indices]
    return samples


def describe(dataset: Any) -> str:
    """One-line class-count summary for the training log."""
    classes = dataset_classes(dataset)
    counts = {name: 0 for name in classes}
    for _, index in dataset_samples(dataset):
        if 0 <= index < len(classes):
            label = classes[index]
            counts[label] = counts.get(label, 0) + 1
    rendered = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    return f"{len(dataset)} images ({rendered})"
