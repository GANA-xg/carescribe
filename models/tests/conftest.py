"""Shared pytest fixtures.

Tests must be reproducible on any machine, with no GPU, no network and no
multi-GB downloads. To guarantee that, this module forces the environment
*before* anything imports :mod:`config`:

* ``ENABLE_HEAVY_MODELS=false`` — services go straight to their documented
  fallbacks instead of attempting to download weights. Tests therefore verify
  the degraded contract, which is the path a fresh clone actually takes.
* ``WARMUP_ON_STARTUP=false`` — models resolve on first request, so the suite
  makes no background network calls.
* Every writable path (weights, logs, reports, inference DB) points inside a
  throwaway temp directory.

Tests that need a real backend are marked ``heavy`` and skip without it.
"""

from __future__ import annotations

import base64
import io
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterator

# --- environment must be pinned before `config` is imported anywhere ---------
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="carescribe-models-tests-"))
(_TMP_ROOT / "logs").mkdir(parents=True, exist_ok=True)

os.environ["ENABLE_HEAVY_MODELS"] = "false"
os.environ["WARMUP_ON_STARTUP"] = "false"
os.environ["WEIGHTS_DIR"] = str(_TMP_ROOT / "weights")
os.environ["LOGS_DIR"] = str(_TMP_ROOT / "logs")
os.environ["REPORTS_DIR"] = str(_TMP_ROOT / "reports")
os.environ["INFERENCE_DB"] = str(_TMP_ROOT / "logs" / "inference.db")
os.environ["LIVENESS_THRESHOLD"] = "0.5"
os.environ.setdefault("DEVICE", "cpu")

# Let tests import sibling helpers without making `tests` a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402  (import after environment pinning, deliberately)


# --------------------------------------------------------------------------
# Synthetic inputs — tests must never ship real patient data.
# --------------------------------------------------------------------------

def make_png_b64(width: int = 512, height: int = 512, colour: str = "white") -> str:
    """A synthetic PNG, base64-encoded, for imaging endpoints."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def make_jpeg_b64(width: int = 640, height: int = 480, colour: str = "white") -> str:
    """A synthetic JPEG; exercises a second decoder path."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def make_wav_b64(duration_s: float = 1.0) -> str:
    """A valid silent WAV, for the STT/TTS endpoints."""
    from utils.audio import silence_wav_b64

    return silence_wav_b64(duration_s)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def image_factory():
    """``image_factory(width, height, colour) -> base64 PNG``."""
    return make_png_b64


@pytest.fixture(scope="session")
def png_b64() -> str:
    return make_png_b64(512, 512)


@pytest.fixture(scope="session")
def jpeg_b64() -> str:
    return make_jpeg_b64(640, 480)


@pytest.fixture(scope="session")
def wav_b64() -> str:
    return make_wav_b64(1.0)


@pytest.fixture(scope="session")
def client() -> Iterator["object"]:
    """A TestClient sharing one app instance across the session."""
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def fresh_client() -> Iterator["object"]:
    """A TestClient on a clean registry.

    Use when a test asserts on model state — for example that ``/health``
    reports an empty model list before anything has loaded.
    """
    from fastapi.testclient import TestClient

    from main import create_app
    from utils.registry import registry

    registry.reset()
    with TestClient(create_app()) as test_client:
        yield test_client
    registry.reset()


@pytest.fixture()
def isolated_log() -> Iterator["object"]:
    """Point the inference log at a temp database for the duration of a test."""
    from utils.logging_db import reset_log

    with tempfile.TemporaryDirectory() as directory:
        yield reset_log(Path(directory) / "inference.db")


@pytest.fixture()
def sample_prescription_text() -> str:
    """A representative prescription with lexicon and unseen drug names."""
    return (
        "Dr. A. Sharma, MBBS\n"
        "Patient: Ravi K, 42/M\n"
        "Diagnosis: Acute pharyngitis\n"
        "Rx:\n"
        "1. Tab. Dolo 650 mg  1-0-1  after food  x 5 days\n"
        "2. Cap. Augmentin 625 mg  BD  x 5 days\n"
        "3. Syp. Cetrizine 5 ml  HS  x 3 days\n"
    )
