"""RAG assistant service — pgvector store + LLM. OC-12.

Design:
  * Each patient's HealthRecords + Prescriptions are chunked, embedded,
    and stored in a dedicated pgvector table (rag_chunks).
  * Embedding uses the model service when it exposes one; the fallback
    is a deterministic local embedder so the pipeline is testable
    offline (semantic quality lower, shape identical).
  * The LLM is Anthropic (claude-sonnet-4-6 default) via LLM_API_KEY.
    Without a key, replies fall back to a records-only summary — the
    assistant never invents medical facts it cannot cite.
"""
import os
import uuid
import logging
import math
import hashlib

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database import SessionLocal

logger = logging.getLogger("carescribe.rag")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")
MODEL_SERVICE_URL = os.getenv("MODEL_SERVICE_URL", "http://localhost:9000")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

EMBED_DIM = 384  # matches models service (all-MiniLM-L6-v2) + fallback


async def ensure_rag_table(db: AsyncSession) -> None:
    """Create rag_chunks (idempotent). Called on first assistant use.

    DDL cannot use bound params (asyncpg), so the dimension is formatted
    inline — it's a module constant, never user input.
    """
    await db.execute(text(f"""
        CREATE TABLE IF NOT EXISTS rag_chunks (
            id UUID PRIMARY KEY,
            patient_id UUID NOT NULL,
            source_table TEXT NOT NULL,
            source_id TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding vector({EMBED_DIM}),
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """))
    await db.execute(text(
        "CREATE INDEX IF NOT EXISTS rag_chunks_patient_idx ON rag_chunks (patient_id)"
    ))
    await db.commit()


def _fallback_embed(text: str) -> list[float]:
    """Deterministic bag-of-words hashing embedder (offline test mode).

    Not semantically strong — but stable, fast, and dimensionally sound,
    so the full retrieval pipeline works without network access.
    """
    vec = [0.0] * EMBED_DIM
    for word in text.lower().split():
        h = int(hashlib.sha256(word.encode()).hexdigest(), 16)  # non-security bucketing
        vec[h % EMBED_DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


async def embed(text: str) -> list[float]:
    """Embed via the model service; fall back locally on any failure."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{MODEL_SERVICE_URL}/embed",
                json={"texts": [text]},
            )
            if resp.status_code == 200:
                data = resp.json()
                vecs = data.get("embeddings") or data.get("embedding")
                if vecs:
                    return vecs[0] if isinstance(vecs[0], list) else vecs
    except Exception:
        pass
    return _fallback_embed(text)


def _chunk(record_text: str, size: int = 500) -> list[str]:
    """Split a record's text into <=500-char chunks on sentence bounds."""
    if len(record_text) <= size:
        return [record_text]
    chunks = []
    current = ""
    for sentence in record_text.replace("\n", " ").split(". "):
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > size and current:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


async def embed_patient(patient_id: uuid.UUID, force: bool = False) -> int:
    """Chunk + embed all of a patient's records into rag_chunks.

    First call for a patient embeds everything; later calls are no-ops
    unless force=True (called after new records are written).
    """
    async with SessionLocal() as db:
        await ensure_rag_table(db)
        existing = await db.execute(
            text("SELECT COUNT(*) FROM rag_chunks WHERE patient_id = :pid"),
            {"pid": str(patient_id)},
        )
        if existing.scalar() and not force:
            return existing.scalar()

        await db.execute(
            text("DELETE FROM rag_chunks WHERE patient_id = :pid"),
            {"pid": str(patient_id)},
        )

        count = 0
        records = await db.execute(
            text("""
                SELECT 'health_record' AS t, id::text AS sid, type || ': ' || COALESCE(data::text, '') AS body
                FROM health_records WHERE patient_id = :pid
                UNION ALL
                SELECT 'prescription', id::text, 'prescription: ' || COALESCE(raw_text, '') || ' ' || COALESCE(structured_data::text, '')
                FROM prescriptions WHERE patient_id = :pid
            """),
            {"pid": str(patient_id)},
        )
        for t, sid, body in records.all():
            for chunk_text in _chunk(body or ""):
                if not chunk_text.strip():
                    continue
                vec = await embed(chunk_text)
                await db.execute(
                    text("""
                        INSERT INTO rag_chunks (id, patient_id, source_table, source_id, chunk_text, embedding)
                        VALUES (:id, :pid, :st, :sid, :ct, CAST(:ct_vec AS vector))
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "pid": str(patient_id),
                        "st": t,
                        "sid": sid,
                        "ct": chunk_text,
                        "ct_vec": str(vec),
                    },
                )
                count += 1
        await db.commit()
        return count


async def retrieve(patient_id: uuid.UUID, query: str, top_k: int = 5) -> list[dict]:
    """Top-k most similar chunks for a query (cosine via pgvector).

    The query vector is a list of floats serialized safely; the vector
    literal is passed as a bound param and cast with CAST(...) to avoid
    the ':qv::vector' syntax that SQLAlchemy's param parser mishandles.
    """
    async with SessionLocal() as db:
        await ensure_rag_table(db)
        qvec = await embed(query)
        rows = await db.execute(
            text("""
                SELECT source_table, source_id, chunk_text,
                       1 - (embedding <=> CAST(:qv AS vector)) AS similarity
                FROM rag_chunks
                WHERE patient_id = :pid
                ORDER BY embedding <=> CAST(:qv AS vector)
                LIMIT :k
            """),
            {"pid": str(patient_id), "qv": str(qvec), "k": top_k},
        )
        return [
            {
                "source": f"{st}:{sid}",
                "text": chunk,
                "similarity": round(float(sim), 4),
            }
            for st, sid, chunk, sim in rows.all()
        ]


async def call_llm(patient_name: str, query: str, contexts: list[dict],
                   history: list[dict]) -> str | None:
    """Ask the LLM with patient-record context. Returns None on failure
    so the caller can fall back to a records-only reply."""
    if not LLM_API_KEY:
        return None

    context_block = "\n\n".join(
        f"[{c['source']}] {c['text']}" for c in contexts
    ) or "(no records found)"
    history_block = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])

    prompt = f"""You are CareScribe, a health assistant. Answer the patient's question using ONLY the records below. If the records do not contain the answer, say you don't have that information. Never invent medical facts. Be brief and clear, in the language the question uses.

Patient records:
{context_block}

Conversation so far:
{history_block}

Patient ({patient_name}) asks: {query}"""

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                ANTHROPIC_URL,
                headers={
                    "x-api-key": LLM_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if resp.status_code != 200:
                logger.warning("LLM call failed %s: %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            return data.get("content", [{}])[0].get("text")
    except Exception:
        logger.exception("LLM call crashed")
        return None


def fallback_reply(query: str, contexts: list[dict]) -> str:
    """Records-only reply when no LLM key is configured — still cites
    actual patient records (the contract's core promise)."""
    if not contexts:
        return "I couldn't find any of your records yet. Upload a prescription or ask your doctor to add records first."
    lines = ["Here is what your records say about that:", ""]
    for c in contexts[:5]:
        lines.append(f"- {c['text'][:200]} (source: {c['source']})")
    return "\n".join(lines)
