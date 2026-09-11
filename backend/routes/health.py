"""Health routes for routers that need a home before they exist."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/router-health")
def router_health():
    """Simple check that routing works — public."""
    return {"status": "router-ok"}
