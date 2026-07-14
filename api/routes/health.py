"""Liveness endpoint polled by an external uptime monitor (AD-10)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
