"""Runtime configuration for the CareScribe internal model service.

Every value can be overridden with an environment variable so the same code runs
on a laptop CPU, inside docker-compose, or on a GPU box without edits.

The service is internal-only: it binds ``0.0.0.0:9000`` and is deliberately
*absent* from the public port map in docker-compose. Only the backend reaches it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser() if raw and raw.strip() else default


def _torch_device() -> tuple[str, bool]:
    """Return ``(device, gpu_available)`` without hard-depending on torch.

    GPU is always optional: a missing torch install, a missing CUDA driver or an
    Apple Silicon MPS backend all resolve to ``("cpu", False)`` rather than an
    import error.
    """
    requested = os.getenv("DEVICE", "auto").strip().lower()
    try:
        import torch  # type: ignore[import-not-found]
    except Exception:
        return ("cpu", False)

    cuda = bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
    mps = bool(
        getattr(torch.backends, "mps", None)
        and torch.backends.mps.is_available()
    )

    if requested in {"cuda", "gpu"}:
        return ("cuda" if cuda else "cpu", cuda)
    if requested == "mps":
        return ("mps" if mps else "cpu", mps)
    if requested == "cpu":
        return ("cpu", False)
    # auto
    if cuda:
        return ("cuda", True)
    if mps:
        return ("mps", True)
    return ("cpu", False)


@dataclass(frozen=True)
class Settings:
    """Immutable, environment-derived service settings."""

    service_name: str
    service_version: str
    host: str
    port: int

    # --- capability switches ---------------------------------------------
    # When false, heavy backends are never even attempted; every endpoint goes
    # straight to its documented fallback. Useful for CI and for demos on a
    # machine that must not download multi-GB weights mid-presentation.
    enable_heavy_models: bool
    warmup_on_startup: bool

    # --- filesystem -------------------------------------------------------
    weights_dir: Path
    logs_dir: Path
    inference_db: Path
    reports_dir: Path

    # --- thresholds -------------------------------------------------------
    liveness_threshold: float
    max_embed_batch: int
    # A scan this small is rejected before it reaches the CNN.
    min_image_side: int

    # --- compute ----------------------------------------------------------
    device: str
    gpu_available: bool

    @classmethod
    def from_env(cls) -> "Settings":
        device, gpu = _torch_device()
        weights_dir = _env_path("WEIGHTS_DIR", SERVICE_ROOT / "weights")
        logs_dir = _env_path("LOGS_DIR", SERVICE_ROOT / "logs")
        return cls(
            service_name="carescribe-models",
            service_version=os.getenv("SERVICE_VERSION", "0.1.0"),
            host=os.getenv("HOST", "0.0.0.0"),
            port=_env_int("PORT", 9000),
            enable_heavy_models=_env_bool("ENABLE_HEAVY_MODELS", True),
            warmup_on_startup=_env_bool("WARMUP_ON_STARTUP", True),
            weights_dir=weights_dir,
            logs_dir=logs_dir,
            inference_db=_env_path("INFERENCE_DB", logs_dir / "inference.db"),
            reports_dir=_env_path("REPORTS_DIR", SERVICE_ROOT / "reports"),
            liveness_threshold=_env_float("LIVENESS_THRESHOLD", 0.5),
            max_embed_batch=_env_int("MAX_EMBED_BATCH", 100),
            min_image_side=_env_int("MIN_IMAGE_SIDE", 32),
            device=device,
            gpu_available=gpu,
        )

    def ensure_dirs(self) -> None:
        """Create the writable directories the service expects to exist."""
        for directory in (self.weights_dir, self.logs_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)


_SETTINGS: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings.from_env()
    return _SETTINGS
