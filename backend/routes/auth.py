"""Auth routes — register, login, me, refresh. API contract: /auth/*.

POST /auth/register — patient or doctor signup, returns {user, token}
POST /auth/login    — returns {user, token}
GET  /auth/me       — protected, returns {user}
POST /auth/refresh  — exchange a valid token for a fresh one (OC-14)

Rate limited to 10/min per IP (brute-force protection).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, decode_token, get_current_user, hash_password, verify_password
from database import get_db
from models.db import Doctor, Patient, User
from rate_limit import limiter
from schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_LIMIT = "10/minute"


def _user_out_sync(user: User, patient_id, doctor_id) -> UserOut:
    """Serialize with profile ids so clients can hit patient-scoped routes."""
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        patient_id=patient_id,
        doctor_id=doctor_id,
    )


async def _profile_ids(db: AsyncSession, user: User) -> tuple:
    """Resolve Patient/Doctor row ids (lazy loads are unsafe in async)."""
    patient_id = await db.scalar(select(Patient.id).where(Patient.user_id == user.id))
    doctor_id = await db.scalar(select(Doctor.id).where(Doctor.user_id == user.id))
    return patient_id, doctor_id


async def _auth_payload(db: AsyncSession, user: User) -> AuthResponse:
    patient_id, doctor_id = await _profile_ids(db, user)
    return AuthResponse(user=_user_out_sync(user, patient_id, doctor_id), token=create_token(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_LIMIT)
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Create a User (+ Patient/Doctor profile) and issue a JWT.

    Anyone can call. role determines the profile row and dashboard redirect.
    """
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    if body.role == "patient":
        user.patient = Patient()
    else:
        user.doctor = Doctor()
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return await _auth_payload(db, user)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(AUTH_LIMIT)
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Verify password, return {user, token}. Anyone can call."""
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return await _auth_payload(db, user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Return the authenticated user. Protected — any role."""
    patient_id, doctor_id = await _profile_ids(db, user)
    return _user_out_sync(user, patient_id, doctor_id)


@router.post("/refresh", response_model=AuthResponse)
@limiter.limit(AUTH_LIMIT)
async def refresh(request: Request, user: User = Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    """Issue a fresh 7-day token for a still-valid session. Protected.

    Lets the deployment rotate JWT_SECRET: after rotation old tokens
    fail auth; clients re-login or use a not-yet-expired token to refresh
    before the rotation moment.
    """
    return await _auth_payload(db, user)
