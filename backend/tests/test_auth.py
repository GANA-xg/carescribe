"""OC-03 auth tests — register / login / me against the live app + dev DB.

Run inside backend container:
    pytest tests/test_auth.py -v

Uses the real Postgres (test users are rolled back via unique emails;
seeds remain untouched).
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from database import SessionLocal
from main import app
from models.db import User

EMAIL = f"authtest-{uuid.uuid4().hex[:8]}@example.com"
PASSWORD = "testpass123"


@pytest.mark.asyncio
async def test_register_login_me_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # register
        r = await client.post(
            "/auth/register",
            json={"name": "Auth Test", "email": EMAIL, "password": PASSWORD, "role": "patient"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["user"]["email"] == EMAIL
        assert body["user"]["role"] == "patient"
        assert body["token"]

        # login
        r = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200
        token = r.json()["token"]

        # me
        r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == EMAIL


@pytest.mark.asyncio
async def test_register_duplicate_email_409():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/auth/register",
            json={"name": "Dup", "email": EMAIL, "password": PASSWORD, "role": "patient"},
        )
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_login_wrong_password_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/auth/login", json={"email": EMAIL, "password": "wrongpassword"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_without_token_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/auth/me")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_garbage_token_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_doctor_role_gets_doctor_profile():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        email = f"doctest-{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post(
            "/auth/register",
            json={"name": "Doc Test", "email": email, "password": PASSWORD, "role": "doctor"},
        )
        assert r.status_code == 201

        async with SessionLocal() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            assert user.role == "doctor"
