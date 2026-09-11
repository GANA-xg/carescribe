"""HTTP layer — one module per model group.

Routers stay thin: decode and validate the request, call the matching service,
shape the response, record the inference in the log. All model logic lives in
``services/``.

Imports are deferred to :func:`all_routers` so that importing this package never
triggers a model import.
"""

from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter

#: Modules contributing routes. Order only affects OpenAPI grouping.
ROUTER_MODULES: tuple[str, ...] = (
    "health",
    "ocr",
    "ner",
    "faceid",
    "tumor",
    "symptoms",
    "sepsis",
    "embed",
    "stt",
    "tts",
)


def all_routers() -> list[APIRouter]:
    """Import and return every router, failing loudly on a broken module."""
    return [import_module(f"routers.{name}").router for name in ROUTER_MODULES]


__all__ = ["ROUTER_MODULES", "all_routers"]
