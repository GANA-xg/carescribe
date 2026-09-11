"""Model-serving layer — one module per model group.

Every module exposes a module-level ``SERVICE`` object with:

* ``name``   short identifier used in warmup logs;
* ``models`` the :class:`~utils.loader.LazyModel` instances it owns;
* ``warmup()`` resolve each model, returning ``{key: ok}`` and never raising.

Imports are deferred to :func:`all_services`: heavy dependencies are imported
inside loader callables, so nothing here pulls in torch or transformers at
import time.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelService(Protocol):
    """The shape every service in this package follows."""

    name: str

    def warmup(self) -> dict[str, bool]:
        ...


#: Modules providing a ``SERVICE`` singleton, in warmup order.
SERVICE_MODULES: tuple[str, ...] = (
    "ocr_service",
    "ner_service",
    "faceid_service",
    "tumor_service",
    "symptoms_service",
    "sepsis_service",
    "embed_service",
    "stt_service",
    "tts_service",
)


def all_services() -> list[Any]:
    """Import and return every service singleton, failing loudly if broken."""
    return [import_module(f"services.{name}").SERVICE for name in SERVICE_MODULES]


__all__ = ["ModelService", "SERVICE_MODULES", "all_services"]
