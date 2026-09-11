"""Model architectures shared by the serving layer and the training scripts.

Kept in one module so training and inference can never drift apart: if the
architecture changes here, the loader and every evaluation script follow.

FB-05 uses EfficientNet-B0 with an ImageNet-pretrained backbone and a replaced
4-class head. The brief allows either the referenced repo's CNN or EfficientNet;
EfficientNet-B0 is chosen because ImageNet transfer learning converges on the
~7k-image Kaggle MRI set in a few epochs on a single GPU, and because it is small
enough to run on CPU for the demo.
"""

from __future__ import annotations

from typing import Any

#: Class order is fixed and must match the training folder order. Changing it
#: silently invalidates every saved checkpoint, so it lives in one place.
CLASSES: tuple[str, ...] = ("glioma", "meningioma", "pituitary", "no_tumor")

#: ImageNet statistics; EfficientNet-B0 was pretrained with these.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)

DEFAULT_IMAGE_SIZE = 224


def build_tumor_model(num_classes: int = len(CLASSES), pretrained: bool = True) -> Any:
    """EfficientNet-B0 with a fresh ``num_classes``-way head.

    ``pretrained=True`` downloads ImageNet weights — used for training only.
    Inference loads the fine-tuned checkpoint on top, so it never needs network.
    """
    from torch import nn
    from torchvision import models

    weights = models.EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
    model = models.efficientnet_b0(weights=weights)

    in_features = model.classifier[1].in_features
    model.classifier[1] = nn.Linear(in_features, num_classes)
    return model


def tumor_transform(image_size: int = DEFAULT_IMAGE_SIZE, *, train: bool = False) -> Any:
    """Preprocessing pipeline; the training variant adds augmentation."""
    from torchvision import transforms

    normalise = transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD)
    if not train:
        return transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
                normalise,
            ]
        )
    return transforms.Compose(
        [
            transforms.Resize((image_size, image_size)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.1, contrast=0.1),
            transforms.ToTensor(),
            normalise,
        ]
    )


__all__ = [
    "CLASSES",
    "DEFAULT_IMAGE_SIZE",
    "IMAGENET_MEAN",
    "IMAGENET_STD",
    "build_tumor_model",
    "tumor_transform",
]
