"""Core CareScribe ORM models — OC-02.

Tables:
    users, patients, doctors, prescriptions, health_records,
    face_embeddings, chat_history

Notes:
    * FaceEmbedding.embedding is BYTEA holding a Fernet-encrypted float32
      array — raw face images are NEVER stored (security rule 2).
    * structured_data / data are JSONB so OCR output and health records
      stay schema-flexible.
"""
import datetime
import uuid

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


class User(Base):
    """Login identity. role drives dashboard redirect (patient/doctor)."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # patient | doctor
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

    patient: Mapped["Patient | None"] = relationship(back_populates="user", uselist=False)
    doctor: Mapped["Doctor | None"] = relationship(back_populates="user", uselist=False)


class Patient(Base):
    """Patient profile — 1:1 with User (role=patient)."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    dob: Mapped[datetime.date | None] = mapped_column()
    gender: Mapped[str | None] = mapped_column(String(32))
    blood_type: Mapped[str | None] = mapped_column(String(8))
    openemr_patient_id: Mapped[str | None] = mapped_column(String(64), index=True)

    user: Mapped[User] = relationship(back_populates="patient")
    prescriptions: Mapped[list["Prescription"]] = relationship(back_populates="patient")
    health_records: Mapped[list["HealthRecord"]] = relationship(back_populates="patient")
    face_embedding: Mapped["FaceEmbedding | None"] = relationship(back_populates="patient", uselist=False)
    chat_messages: Mapped[list["ChatHistory"]] = relationship(back_populates="patient")


class Doctor(Base):
    """Doctor profile — 1:1 with User (role=doctor)."""

    __tablename__ = "doctors"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    specialization: Mapped[str | None] = mapped_column(String(120))
    license_number: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship(back_populates="doctor")


class Prescription(Base):
    """A prescription — created after patient confirms OCR output."""

    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    ocr_job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    raw_text: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

    patient: Mapped[Patient] = relationship(back_populates="prescriptions")


class HealthRecord(Base):
    """One entry in the Health Passport — from OCR or manual entry."""

    __tablename__ = "health_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. prescription|lab|diagnosis|imaging|sepsis_score
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")  # ocr | manual
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

    patient: Mapped[Patient] = relationship(back_populates="health_records")


class FaceEmbedding(Base):
    """Encrypted face embedding — NO raw images ever stored."""

    __tablename__ = "face_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, unique=True)
    embedding: Mapped[bytes] = mapped_column(BYTEA, nullable=False)  # Fernet(float32 array)
    model_name: Mapped[str | None] = mapped_column(String(64))
    enrolled_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

    patient: Mapped[Patient] = relationship(back_populates="face_embedding")


class ChatHistory(Base):
    """RAG assistant chat log — one row per message."""

    __tablename__ = "chat_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=_uuid_pk)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

    patient: Mapped[Patient] = relationship(back_populates="chat_messages")
