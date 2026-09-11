"""RAG assistant routes. API contract: /assistant/*. OC-12.

POST /assistant/chat  — grounded answer over the patient's own records,
                       with source citations. Patient (own) or doctor.
POST /assistant/voice — Whisper STT -> chat pipeline -> TTS audio URL.
                       Same access rules as chat.
"""
import base64
import io
import uuid
import wave

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import get_db
from models.db import ChatHistory, Patient, User
from services import rag
from services.model_proxy import ModelServiceError, call_model

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    patient_id: uuid.UUID
    message: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatResponse(BaseModel):
    reply: str
    sources: list[str]
    citations: list[dict]


async def _authorize(patient_id: uuid.UUID, user: User, db: AsyncSession) -> Patient:
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "Patient not found")
    if user.role == "patient" and patient.user_id != user.id:
        raise HTTPException(403, "Not your assistant")
    return patient


def _audio_url(audio_b64: str) -> str:
    """The TTS output is inlined; expose as a data URL the frontend can play."""
    return f"data:audio/wav;base64,{audio_b64}"


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, user: User = Depends(get_current_user),
               db: AsyncSession = Depends(get_db)):
    """Answer a question grounded in the patient's records. Protected."""
    patient = await _authorize(body.patient_id, user, db)

    # Ensure this patient's records are embedded (first call embeds all).
    await rag.embed_patient(body.patient_id)

    contexts = await rag.retrieve(body.patient_id, body.message, top_k=5)

    history = [m.model_dump() for m in body.history]
    reply = await rag.call_llm(patient.user.name, body.message, contexts, history)
    if reply is None:
        reply = rag.fallback_reply(body.message, contexts)

    # Log both turns for future history + RAG context.
    db.add(ChatHistory(patient_id=body.patient_id, role="user", content=body.message))
    db.add(ChatHistory(patient_id=body.patient_id, role="assistant", content=reply))
    await db.commit()

    sources = [c["source"] for c in contexts]
    citations = [
        {"source": c["source"], "text": c["text"][:300], "similarity": c["similarity"]}
        for c in contexts
    ]
    return ChatResponse(reply=reply, sources=sources, citations=citations)


@router.post("/voice")
async def voice(
    audio_file: UploadFile = File(...),
    patient_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Voice loop: STT -> RAG chat -> TTS. Protected.

    patient_id may come as a form field or query param (contract allows
    both shapes). Audio replies are returned as a data URL.
    """
    if patient_id is None:
        raise HTTPException(422, "patient_id is required")

    patient = await _authorize(patient_id, user, db)

    audio = await audio_file.read()
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(413, "Audio exceeds 10MB")

    # 1. STT
    try:
        stt = await call_model("/stt", content=audio, filename=audio_file.filename or "voice.wav")
    except ModelServiceError as e:
        raise HTTPException(502, f"Speech-to-text unavailable: {e}") from e
    transcript = stt.get("transcript", "").strip()
    if not transcript:
        raise HTTPException(422, "Could not transcribe any speech")

    # 2. RAG chat over the transcript (recent history from ChatHistory)
    await rag.embed_patient(patient_id)
    contexts = await rag.retrieve(patient_id, transcript, top_k=5)
    recent = (
        await db.execute(
            select(ChatHistory)
            .where(ChatHistory.patient_id == patient_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(6)
        )
    ).scalars().all()
    history = [{"role": m.role, "content": m.content} for m in reversed(recent)]

    reply = await rag.call_llm(patient.user.name, transcript, contexts, history)
    if reply is None:
        reply = rag.fallback_reply(transcript, contexts)

    db.add(ChatHistory(patient_id=patient_id, role="user", content=transcript))
    db.add(ChatHistory(patient_id=patient_id, role="assistant", content=reply))
    await db.commit()

    # 3. TTS (best effort — text reply still returned if TTS fails)
    audio_reply_url = None
    try:
        tts = await call_model("/tts", json_body={"text": reply})
        audio_reply_url = _audio_url(tts.get("audio_b64", ""))
    except ModelServiceError:
        audio_reply_url = None

    return {
        "transcript": transcript,
        "reply": reply,
        "audio_reply_url": audio_reply_url,
        "sources": [c["source"] for c in contexts],
    }
