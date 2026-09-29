from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings
from app.config import Settings
from app.models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    """Liveness/readiness probe for load balancers, Docker healthchecks, k8s."""
    return HealthResponse(status="ok", app_env=settings.app_env, claude_model=settings.claude_model)
