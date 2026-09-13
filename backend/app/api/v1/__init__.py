"""Version 1 of the public API."""

from fastapi import APIRouter

from app.api.v1 import health, replays, analytics

router = APIRouter()
router.include_router(health.router, tags=["health"])
router.include_router(replays.router, prefix="/replays", tags=["replays"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

__all__ = ["router"]
