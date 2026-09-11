"""Seed script — creates one test patient and one test doctor.

Run inside the backend container:
    python seed.py

Idempotent: skips if the seed emails already exist.
"""
import asyncio

from passlib.context import CryptContext
from sqlalchemy import select

from database import SessionLocal
from models.db import Doctor, Patient, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TEST_PATIENT = {
    "name": "Test Patient",
    "email": "patient@example.com",
    "password": "patientpass123",
}

TEST_DOCTOR = {
    "name": "Test Doctor",
    "email": "doctor@example.com",
    "password": "doctorpass123",
    "specialization": "Internal Medicine",
    "license_number": "REG-TEST-0001",
}


async def seed() -> None:
    async with SessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == TEST_PATIENT["email"]))
        if existing:
            print(f"Seed already present (user {existing.email}) — skipping.")
            return

        patient_user = User(
            name=TEST_PATIENT["name"],
            email=TEST_PATIENT["email"],
            password_hash=pwd_context.hash(TEST_PATIENT["password"]),
            role="patient",
        )
        patient = Patient(user=patient_user, gender="male", blood_type="O+")
        session.add(patient_user)

        doctor_user = User(
            name=TEST_DOCTOR["name"],
            email=TEST_DOCTOR["email"],
            password_hash=pwd_context.hash(TEST_DOCTOR["password"]),
            role="doctor",
        )
        doctor = Doctor(
            user=doctor_user,
            specialization=TEST_DOCTOR["specialization"],
            license_number=TEST_DOCTOR["license_number"],
        )
        session.add(doctor_user)

        await session.commit()
        print("Seeded:")
        print(f"  patient: {TEST_PATIENT['email']} / {TEST_PATIENT['password']}")
        print(f"  doctor:  {TEST_DOCTOR['email']} / {TEST_DOCTOR['password']}")


if __name__ == "__main__":
    asyncio.run(seed())
