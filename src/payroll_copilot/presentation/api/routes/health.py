"""Health check routes."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def api_health() -> dict[str, str]:
    return {"status": "healthy"}
