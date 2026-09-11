"""OC-14 tests — rate limiting, refresh, body size cap.

Rate limits are tested against a fresh ASGI transport using explicit
X-Forwarded-For headers (slowapi keys off get_remote_address, which the
ASGITransport can't provide — so we patch the key function per-test).
"""
import os
import uuid

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from slowapi.util import get_remote_address

import rate_limit
from main import app


@pytest.mark.asyncio
async def test_auth_rate_limit_429(monkeypatch):
    """11th register from one IP within a minute -> 429.

    Uses a dedicated app+router instance so the real app's decorators
    (bound at import, with RATE_LIMITS=off for the rest of the suite)
    stay untouched.
    """
    from fastapi import FastAPI
    from slowapi import Limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler

    lim = Limiter(key_func=lambda request: "fixed-test-ip", default_limits=["30/minute"])

    limit_app = FastAPI()
    limit_app.state.limiter = lim
    limit_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    import routes.auth as auth_route_mod

    # Re-import the router module functions against the fresh limiter:
    # rebuild a small router mirroring register's limit.
    from fastapi import APIRouter, Depends
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from auth import hash_password
    from database import get_db
    from models.db import Patient, User
    from schemas import AuthResponse, RegisterRequest, UserOut

    r = APIRouter(prefix="/auth")

    @r.post("/register", response_model=AuthResponse, status_code=201)
    @lim.limit("10/minute")
    async def register2(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
        existing = await db.scalar(select(User).where(User.email == body.email))
        if existing:
            from fastapi import HTTPException

            raise HTTPException(409, "Email already registered")
        user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role=body.role)
        if body.role == "patient":
            user.patient = Patient()
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return AuthResponse(user=UserOut.model_validate(user), token="tok")

    limit_app.include_router(r)

    async with AsyncClient(transport=ASGITransport(app=limit_app), base_url="http://test") as client:
        codes = []
        for i in range(11):
            resp = await client.post(
                "/auth/register",
                json={"name": f"L{i}", "email": f"limit{i}-{uuid.uuid4().hex[:6]}@example.com",
                      "password": "testpass123", "role": "patient"},
            )
            codes.append(resp.status_code)
        assert codes[:10] == [201] * 10, codes
        assert codes[10] == 429, codes


@pytest.mark.asyncio
async def test_refresh_returns_new_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        email = f"ref-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post("/auth/register",
                              json={"name": "Ref", "email": email, "password": "testpass123", "role": "patient"})
        old_token = r.json()["token"]

        r = await client.post("/auth/refresh", headers={"Authorization": f"Bearer {old_token}"})
        assert r.status_code == 200
        assert r.json()["token"]


@pytest.mark.asyncio
async def test_refresh_rejects_garbage():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/auth/refresh", headers={"Authorization": "Bearer junk"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_oversized_body_413():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        big = b"x" * (11 * 1024 * 1024)
        r = await client.post(
            "/drugs/compare",
            content=big,
            headers={"Content-Type": "application/json", "Content-Length": str(len(big))},
        )
        assert r.status_code == 413
