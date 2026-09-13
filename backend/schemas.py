"""Pydantic schemas — shared across routes (API contract shapes)."""
import uuid
import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: Literal["patient", "doctor"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)


class UserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: EmailStr
    role: str
    created_at: datetime.datetime
    # Profile row ids — the patient_id every /passport, /prescriptions,
    # /imaging and /assistant endpoint expects in its path.
    patient_id: uuid.UUID | None = None
    doctor_id: uuid.UUID | None = None

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    user: UserOut
    token: str


class TokenRefreshRequest(BaseModel):
    # OC-14 adds POST /auth/refresh using a still-valid token.
    token: str


class OcrResult(BaseModel):
    raw_text: str
    structured: dict
    model_used: str
    confidence: float


class OcrStatusResponse(BaseModel):
    status: str
    result: Optional[OcrResult] = None
