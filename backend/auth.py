"""JWT helpers + password hashing + FastAPI auth dependencies.

Token: HS256, 7-day expiry, sub=user_id, role=role.
Secret: JWT_SECRET env var (never hardcode).
"""
import os
import uuid
import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db import User

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """bcrypt hash — truncation happens >72 bytes, validated upstream."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verify."""
    return pwd_context.verify(plain, hashed)


def create_token(user: User) -> str:
    """Issue a 7-day JWT with sub=user_id, role=role."""
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=JWT_EXPIRY_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + validate. Raises 401 on any failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from e


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency: any authenticated user (patient or doctor)."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    payload = decode_token(credentials.credentials)
    user_id = uuid.UUID(payload["sub"])
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")
    return user


async def require_doctor(user: User = Depends(get_current_user)) -> User:
    """Dependency: doctor-only routes."""
    if user.role != "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Doctor access only")
    return user


async def require_patient(user: User = Depends(get_current_user)) -> User:
    """Dependency: patient-only routes."""
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Patient access only")
    return user
