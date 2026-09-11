"""Auth routes — register, login, me. API contract: /auth/*.

POST /auth/register — patient or doctor signup, returns {user, token}
POST /auth/login    — returns {user, token}
GET  /auth/me       — protected, returns {user}
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_token, get_current_user, hash_password, verify_password
from database import get_db
from models.db import Doctor, Patient, User
from schemas import AuthResponse, LoginRequest, RegisterRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_payload(user: User) -> AuthResponse:
    return AuthResponse(user=UserOut.model_validate(user), token=create_token(user))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
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
    return _auth_payload(user)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Verify password, return {user, token}. Anyone can call."""
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _auth_payload(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    """Return the authenticated user. Protected — any role."""
    return UserOut.model_validate(user)
