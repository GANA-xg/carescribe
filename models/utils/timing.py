"""Timing helpers.

Rule 5 of the FreeBuff brief: every response carries ``inference_time_ms`` and a
``model_version``, because the research paper reports per-model latency. The
timer here is the only place wall-clock inference time is measured.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone


def now_iso() -> str:
    """UTC timestamp in ISO-8601, second precision, ``Z``-suffixed."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class InferenceTimer:
    """Context manager measuring elapsed wall-clock milliseconds.

    >>> with InferenceTimer() as t:
    ...     pass
    >>> t.elapsed_ms >= 0.0
    True
    """

    __slots__ = ("_start", "elapsed_ms")

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "InferenceTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0

    def stop(self) -> float:
        """Stop the timer early and return the elapsed milliseconds."""
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        return self.elapsed_ms


def round_ms(value: float) -> float:
    """Round latency for stable, human-readable responses."""
    return round(float(value), 2)
