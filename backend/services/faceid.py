"""Face-ID matching service — FAISS index over encrypted embeddings. OC-07.

Security rules:
  * Raw images are NEVER stored — only the embedding vector, and only
    Fernet-encrypted at rest (BYTEA in face_embeddings).
  * Decryption happens only in memory, transiently, for FAISS search.
  * The FAISS index is rebuilt from the DB every REFRESH_SECONDS (5 min)
    so enroll/unenroll converge without restarts.
"""
import base64
import hashlib
import os
import threading
import time
import uuid

import faiss
import numpy as np
from cryptography.fernet import Fernet
from sqlalchemy import select

from database import SessionLocal
from models.db import FaceEmbedding, Patient, User


def _load_fernet() -> Fernet:
    """Use FERNET_KEY if set; otherwise derive a deterministic dev key."""
    raw = os.getenv("FERNET_KEY", "")
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception:
            pass
    digest = hashlib.sha256(b"carescribe-dev-fernet").digest()
    return Fernet(base64.urlsafe_b64encode(digest))


_fernet = _load_fernet()

DIM = 512  # ArcFace output dim (models service returns 512-d embeddings)
REFRESH_SECONDS = 300  # rebuild index every 5 minutes

_lock = threading.Lock()
_index: faiss.IndexFlatIP | None = None
_ids: list[uuid.UUID] = []
_names: dict[uuid.UUID, str] = {}
_last_built = 0.0


def encrypt_embedding(vec: list[float]) -> bytes:
    """Encrypt a float32 embedding with Fernet."""
    raw = np.asarray(vec, dtype=np.float32).tobytes()
    return _fernet.encrypt(raw)


def decrypt_embedding(blob: bytes) -> np.ndarray:
    """Decrypt back to a float32 numpy vector."""
    raw = _fernet.decrypt(blob)
    return np.frombuffer(raw, dtype=np.float32)


def _normalize(vec: np.ndarray) -> np.ndarray:
    """L2-normalize so IndexFlatIP gives cosine similarity."""
    norm = np.linalg.norm(vec)
    return vec if norm == 0 else vec / norm


async def rebuild_index(force: bool = False) -> None:
    """Load all stored (encrypted) embeddings, build a FAISS index.

    Called on startup, after enroll/unenroll, and every 5 minutes from
    the route layer (opportunistic refresh — avoids a background thread
    fighting with tests).
    """
    global _index, _ids, _names, _last_built

    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(FaceEmbedding.patient_id, FaceEmbedding.embedding, User.name)
                .join(Patient, Patient.id == FaceEmbedding.patient_id)
                .join(User, User.id == Patient.user_id)
            )
        ).all()

    vectors = []
    ids = []
    names = {}
    for patient_id, blob, user_name in rows:
        try:
            vec = _normalize(decrypt_embedding(blob))
            if vec.shape[0] != DIM:
                continue
            vectors.append(vec)
            ids.append(patient_id)
            names[patient_id] = user_name
        except Exception:
            continue  # skip undecryptable rows (key rotation leftovers)

    with _lock:
        if vectors:
            index = faiss.IndexFlatIP(DIM)
            index.add(np.vstack(vectors).astype(np.float32))
            _index = index
        else:
            _index = None
        _ids = ids
        _names = names
        _last_built = time.time()
        _ = force  # unused, kept for API clarity


def maybe_refresh() -> bool:
    """Return True if the index is stale (>5 min since last build)."""
    return time.time() - _last_built > REFRESH_SECONDS


def search(vec: list[float], top_k: int = 1) -> tuple[uuid.UUID | None, str | None, float]:
    """Search for the closest enrolled face.

    Returns (patient_id, name, cosine similarity) or (None, None, 0.0)
    when the index is empty. Similarity is in [-1, 1].
    """
    if _index is None or not _ids:
        return None, None, 0.0
    q = _normalize(np.asarray(vec, dtype=np.float32)).reshape(1, -1)
    with _lock:
        scores, idxs = _index.search(q, min(top_k, len(_ids)))
    best_score = float(scores[0][0])
    best_idx = int(idxs[0][0])
    if best_idx < 0:
        return None, None, 0.0
    pid = _ids[best_idx]
    return pid, _names.get(pid), best_score
