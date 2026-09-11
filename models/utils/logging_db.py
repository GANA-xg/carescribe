"""SQLite-backed inference log.

FB-12 requires every inference call to be recorded — model, latency, input size
and output confidence — so the project report can quote real numbers instead of
estimates, and ``scripts/inference_report.py`` can summarise them.

Two hard rules:

* **Logging never breaks a request.** Every write is wrapped; a locked database
  or a full disk costs us a log line, never a 500.
* **No patient data.** Only sizes, timings, confidences and error strings are
  stored — never images, transcripts or record contents.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import get_settings
from utils.timing import now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inference_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ts               TEXT    NOT NULL,
    model_key        TEXT    NOT NULL,
    model_id         TEXT,
    endpoint         TEXT    NOT NULL,
    inference_time_ms REAL,
    input_size       TEXT,
    confidence       REAL,
    degraded         INTEGER NOT NULL DEFAULT 0,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS idx_inference_ts    ON inference_log (ts);
CREATE INDEX IF NOT EXISTS idx_inference_model ON inference_log (model_key);
"""


@dataclass(frozen=True)
class InferenceRow:
    ts: str
    model_key: str
    model_id: str | None
    endpoint: str
    inference_time_ms: float | None
    input_size: str | None
    confidence: float | None
    degraded: bool
    error: str | None


class InferenceLog:
    """Append-only inference log on top of sqlite3."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._ready = False

    # --- plumbing ---------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        return connection

    def initialise(self) -> bool:
        """Create the schema. Returns False if the file is not writable."""
        with self._lock:
            try:
                with self._connect() as connection:
                    connection.executescript(_SCHEMA)
                self._ready = True
            except sqlite3.Error:
                self._ready = False
            return self._ready

    @property
    def ready(self) -> bool:
        return self._ready

    # --- writing ----------------------------------------------------------
    def record(
        self,
        *,
        model_key: str,
        endpoint: str,
        inference_time_ms: float | None = None,
        model_id: str | None = None,
        input_size: str | None = None,
        confidence: float | None = None,
        degraded: bool = False,
        error: str | None = None,
    ) -> None:
        """Append one row. Silently gives up if the database is unusable."""
        try:
            if not self._ready:
                self.initialise()
            if not self._ready:
                return
            row = (
                now_iso(),
                model_key,
                model_id,
                endpoint,
                None if inference_time_ms is None else round(float(inference_time_ms), 3),
                input_size,
                None if confidence is None else round(float(confidence), 4),
                1 if degraded else 0,
                error,
            )
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT INTO inference_log (ts, model_key, model_id, endpoint,"
                    " inference_time_ms, input_size, confidence, degraded, error)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    row,
                )
        except Exception:  # noqa: BLE001 - logging must never break a request
            return

    # --- reading ----------------------------------------------------------
    def rows(self, limit: int = 1000) -> list[InferenceRow]:
        if not self._ready:
            self.initialise()
        if not self._ready:
            return []
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "SELECT ts, model_key, model_id, endpoint, inference_time_ms,"
                    " input_size, confidence, degraded, error"
                    " FROM inference_log ORDER BY id DESC LIMIT ?",
                    (int(limit),),
                )
                return [
                    InferenceRow(
                        ts=item["ts"],
                        model_key=item["model_key"],
                        model_id=item["model_id"],
                        endpoint=item["endpoint"],
                        inference_time_ms=item["inference_time_ms"],
                        input_size=item["input_size"],
                        confidence=item["confidence"],
                        degraded=bool(item["degraded"]),
                        error=item["error"],
                    )
                    for item in cursor.fetchall()
                ]
        except sqlite3.Error:
            return []

    def per_model_summary(self) -> list[dict[str, Any]]:
        """Call count, mean latency and degradation rate per model."""
        if not self._ready:
            self.initialise()
        if not self._ready:
            return []
        query = """
            SELECT model_key,
                   COUNT(*)                              AS calls,
                   AVG(inference_time_ms)                AS avg_ms,
                   MIN(inference_time_ms)                AS min_ms,
                   MAX(inference_time_ms)                AS max_ms,
                   AVG(confidence)                       AS avg_confidence,
                   SUM(degraded)                         AS degraded_calls,
                   SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) AS errors
            FROM inference_log
            GROUP BY model_key
            ORDER BY calls DESC
        """
        try:
            with self._connect() as connection:
                cursor = connection.execute(query)
                return [
                    {
                        "model_key": row["model_key"],
                        "calls": row["calls"],
                        "avg_ms": round(row["avg_ms"], 2) if row["avg_ms"] is not None else None,
                        "min_ms": row["min_ms"],
                        "max_ms": row["max_ms"],
                        "avg_confidence": (
                            round(row["avg_confidence"], 4)
                            if row["avg_confidence"] is not None
                            else None
                        ),
                        "degraded_calls": row["degraded_calls"] or 0,
                        "errors": row["errors"] or 0,
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error:
            return []

    def endpoint_summary(self) -> list[dict[str, Any]]:
        """Call count and mean latency per endpoint."""
        if not self._ready:
            self.initialise()
        if not self._ready:
            return []
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    "SELECT endpoint, COUNT(*) AS calls, AVG(inference_time_ms) AS avg_ms"
                    " FROM inference_log GROUP BY endpoint ORDER BY calls DESC"
                )
                return [
                    {
                        "endpoint": row["endpoint"],
                        "calls": row["calls"],
                        "avg_ms": round(row["avg_ms"], 2) if row["avg_ms"] is not None else None,
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error:
            return []


#: Process-wide log instance, created lazily so tests can point it elsewhere.
_LOG: InferenceLog | None = None


def get_log() -> InferenceLog:
    global _LOG
    if _LOG is None:
        _LOG = InferenceLog(get_settings().inference_db)
        _LOG.initialise()
    return _LOG


def reset_log(path: Path | str | None = None) -> InferenceLog:
    """Rebuild the singleton, optionally against a new path. Test helper."""
    global _LOG
    _LOG = InferenceLog(path or get_settings().inference_db)
    _LOG.initialise()
    return _LOG


def record_inference(
    *,
    model_key: str,
    endpoint: str,
    inference_time_ms: float | None = None,
    input_size: str | None = None,
    confidence: float | None = None,
    degraded: bool = False,
    error: str | None = None,
) -> None:
    """Convenience wrapper that resolves the model version for the log row."""
    try:
        from catalog import model_id as catalog_model_id
        from utils.registry import registry

        state = registry.get(model_key)
        # Keys like 'ocr_merge' and 'tts_silent' are pure-Python components with
        # no LazyModel, so they never appear in the registry. The catalog still
        # knows their version, which keeps the log complete.
        model_id = state.model_id if state else catalog_model_id(model_key)
        if state is not None and not degraded:
            degraded = state.degraded
    except Exception:  # noqa: BLE001
        model_id = None

    get_log().record(
        model_key=model_key,
        model_id=model_id,
        endpoint=endpoint,
        inference_time_ms=inference_time_ms,
        input_size=input_size,
        confidence=confidence,
        degraded=degraded,
        error=error,
    )
