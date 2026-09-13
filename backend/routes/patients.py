"""Doctor dashboard routes: list patients + recent activity. CL-07.

GET /patients — doctor-only. Every patient with their latest health
record timestamp so the doctor dashboard can show "last visit".
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_doctor
from database import get_db
from models.db import HealthRecord, Patient, User

router = APIRouter(prefix="", tags=["doctor"])


@router.get("/patients")
async def list_patients(
    doctor: User = Depends(require_doctor),
    db: AsyncSession = Depends(get_db),
):
    """All patients with name + last record time. DOCTOR-ONLY."""
    latest = (
        select(
            HealthRecord.patient_id.label("pid"),
            func.max(HealthRecord.created_at).label("last_record"),
        )
        .group_by(HealthRecord.patient_id)
        .subquery()
    )

    rows = (
        await db.execute(
            select(Patient.id, User.name, User.email, latest.c.last_record)
            .join(User, Patient.user_id == User.id)
            .outerjoin(latest, latest.c.pid == Patient.id)
            .order_by(User.name)
        )
    ).all()

    return {
        "patients": [
            {
                "id": str(pid),
                "name": name,
                "email": email,
                "last_visit": last.isoformat() if last else None,
            }
            for pid, name, email, last in rows
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
