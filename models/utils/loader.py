"""Load-once model holder with graceful degradation.

Rule 2 of the FreeBuff brief says models load once, never per request. Rule 6
says GPU is optional and CPU must always work. This class enforces both:

* the loader runs at most once, guarded by a lock;
* if it raises — missing package, no network, corrupt weights, no GPU — and a
  ``fallback`` was supplied, the fallback takes over and the model is recorded
  as ``degraded`` with the original error message attached.

Endpoints whose answers must never be fabricated (face identity, tumour
classification) pass no fallback and opt into a hard failure instead.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

from catalog import spec
from config import get_settings
from utils.registry import registry
from utils.timing import InferenceTimer


class LazyModel:
    """A model that is resolved on first use and then cached forever."""

    def __init__(
        self,
        key: str,
        loader: Callable[[], Any],
        *,
        fallback: Callable[[], Any] | None = None,
        fallback_key: str | None = None,
        note: str | None = None,
    ) -> None:
        self.spec = spec(key)
        self.key = key
        self.fallback_key = fallback_key
        self._loader = loader
        self._fallback = fallback
        self._note = note
        self._lock = threading.RLock()
        self._value: Any = None
        self._resolved = False
        self._serving_fallback = False
        self._load_ms: float | None = None
        self._generation = -1
        self.last_error: str | None = None
        registry.declare(key)

    # --- introspection ----------------------------------------------------
    @property
    def available(self) -> bool:
        """True once resolved from the *real* model rather than a fallback."""
        return self._resolved and not self._serving_fallback

    @property
    def resolved(self) -> bool:
        return self._resolved

    @property
    def serving_fallback(self) -> bool:
        return self._serving_fallback

    @property
    def value(self) -> Any:
        return self.load()

    def status_reason(self) -> str:
        """Human-readable explanation of the current state, for reports."""
        if not self._resolved:
            return "not loaded yet"
        if self._serving_fallback:
            return f"degraded: {self.last_error}"
        return "loaded"

    # --- resolution -------------------------------------------------------
    def load(self) -> Any:
        """Return the model, loading it (or its fallback) on first call."""
        with self._lock:
            if self._resolved:
                if self._generation != registry.generation:
                    # The registry was cleared (e.g. by tooling or /health tests)
                    # while this model stayed warm. Re-announce it rather than
                    # reloading it, so /health reflects reality.
                    self._announce()
                return self._value

            settings = get_settings()
            if self.spec.heavy and not settings.enable_heavy_models and self._fallback is not None:
                # Deliberate degraded mode: never even attempt the heavy import.
                return self._use_fallback("heavy models disabled (ENABLE_HEAVY_MODELS=false)")

            registry.set_loading(self.key)
            timer = InferenceTimer()
            try:
                with timer:
                    value = self._loader()
            except Exception as exc:  # noqa: BLE001 - any failure means degrade
                reason = f"{type(exc).__name__}: {exc}"
                if self._fallback is None:
                    registry.set_failed(self.key, reason)
                    self.last_error = reason
                    raise
                return self._use_fallback(reason, load_ms=timer.elapsed_ms)

            self._value = value
            self._resolved = True
            self._serving_fallback = False
            self._load_ms = timer.elapsed_ms
            self.last_error = None
            self._announce()
            return self._value

    def _use_fallback(self, reason: str, load_ms: float | None = None) -> Any:
        """Resolve to the fallback backend and record the degradation."""
        assert self._fallback is not None  # guarded by callers
        self.last_error = reason
        try:
            self._value = self._fallback()
        except Exception as exc:  # noqa: BLE001
            registry.set_failed(self.key, f"fallback failed: {type(exc).__name__}: {exc}")
            raise
        self._resolved = True
        self._serving_fallback = True
        self._load_ms = load_ms
        self._announce()
        return self._value

    def _announce(self) -> None:
        """(Re-)record this model's state in the registry.

        Called after resolution and again whenever the registry's generation
        changes, so bookkeeping survives a reset without reloading the model.
        """
        if self._serving_fallback:
            registry.set_degraded(self.key, self.last_error or "fallback in use", note=self._note)
            if self.fallback_key:
                # Surface the fallback as a loaded model too, so /health shows
                # both "medspacy: degraded" and "ner_regex: loaded".
                registry.set_loaded(
                    self.fallback_key, note=f"serving in place of {self.key}"
                )
        else:
            registry.set_loaded(self.key, load_ms=self._load_ms, note=self._note)
        self._generation = registry.generation

    def warm(self) -> bool:
        """Resolve the model and report whether the *real* backend loaded.

        ``False`` means either the fallback took over (degraded) or the model is
        unavailable — the registry carries which, and why. Never raises: startup
        must not fail because one model is missing, and endpoints use this to
        decide whether they can serve a real answer.
        """
        try:
            self.load()
        except Exception:  # noqa: BLE001
            return False
        return self.available
