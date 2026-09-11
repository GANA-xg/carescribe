"""Process-wide registry of model state, versions and load times.

FB-12 asks ``/health`` to report every loaded model with its version and load
time. This module is the bookkeeping behind that: each model declares itself
against the catalog, then records one of a small set of lifecycle states.

``degraded`` is the important one. It means *the endpoint is serving, but from a
fallback rather than the real model*. Callers can therefore distinguish "the
tumour model said no_tumor" from "the tumour model isn't installed", which a
bare boolean would hide.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from catalog import spec
from utils.timing import now_iso


class ModelStatus(str, Enum):
    NOT_LOADED = "not_loaded"
    LOADING = "loading"
    LOADED = "loaded"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass
class ModelState:
    key: str
    model_id: str
    backend: str
    source: str
    heavy: bool
    status: ModelStatus = ModelStatus.NOT_LOADED
    loaded_at: str | None = None
    load_ms: float | None = None
    reason: str | None = None
    note: str | None = None

    @property
    def serving(self) -> bool:
        """True when this model is answering requests (real or fallback)."""
        return self.status in {ModelStatus.LOADED, ModelStatus.DEGRADED}

    @property
    def degraded(self) -> bool:
        return self.status in {ModelStatus.DEGRADED, ModelStatus.FAILED}

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["serving"] = self.serving
        payload["degraded"] = self.degraded
        return payload


class ModelRegistry:
    """Thread-safe registry; one instance per process."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states: dict[str, ModelState] = {}
        # Bumped by reset(). LazyModel compares this against the generation it
        # resolved in, so a cleared registry is repopulated by cached models on
        # their next call instead of silently reporting an empty inventory.
        self._generation = 0

    # --- lifecycle --------------------------------------------------------
    def declare(self, key: str) -> ModelState:
        """Register a model from the catalog (idempotent)."""
        with self._lock:
            existing = self._states.get(key)
            if existing is not None:
                return existing
            item = spec(key)
            state = ModelState(
                key=item.key,
                model_id=item.model_id,
                backend=item.backend,
                source=item.source,
                heavy=item.heavy,
            )
            self._states[key] = state
            return state

    def set_loading(self, key: str) -> None:
        with self._lock:
            state = self.declare(key)
            state.status = ModelStatus.LOADING
            state.reason = None

    def set_loaded(self, key: str, load_ms: float | None = None, note: str | None = None) -> None:
        with self._lock:
            state = self.declare(key)
            state.status = ModelStatus.LOADED
            state.loaded_at = now_iso()
            state.load_ms = round(load_ms, 2) if load_ms is not None else None
            state.reason = None
            if note:
                state.note = note

    def set_degraded(self, key: str, reason: str, note: str | None = None) -> None:
        """Mark a model as serving a fallback, recording why."""
        with self._lock:
            state = self.declare(key)
            state.status = ModelStatus.DEGRADED
            state.loaded_at = now_iso()
            state.reason = reason
            if note:
                state.note = note

    def set_failed(self, key: str, reason: str) -> None:
        with self._lock:
            state = self.declare(key)
            state.status = ModelStatus.FAILED
            state.reason = reason

    # --- queries ----------------------------------------------------------
    def get(self, key: str) -> ModelState | None:
        with self._lock:
            return self._states.get(key)

    def status_of(self, key: str) -> ModelStatus:
        state = self.get(key)
        return state.status if state else ModelStatus.NOT_LOADED

    def loaded_keys(self) -> list[str]:
        """Keys currently answering requests, in declaration order."""
        with self._lock:
            return [k for k, s in self._states.items() if s.serving]

    def snapshot(self) -> list[dict[str, Any]]:
        """Full detail for every declared model, for ``/health`` and reports."""
        with self._lock:
            return [state.as_dict() for state in self._states.values()]

    @property
    def generation(self) -> int:
        """Monotonic counter identifying the current registry incarnation."""
        with self._lock:
            return self._generation

    def reset(self) -> None:
        """Drop all state and invalidate cached models' bookkeeping."""
        with self._lock:
            self._states.clear()
            self._generation += 1


#: Process-wide singleton.
registry = ModelRegistry()
