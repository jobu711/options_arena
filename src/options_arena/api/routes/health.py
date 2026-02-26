"""Health check endpoints — basic liveness + full service check."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from options_arena.api.deps import get_settings
from options_arena.models import AppSettings, HealthStatus
from options_arena.services.health import HealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness check."""
    return {"status": "ok"}


@router.get("/health/services")
async def check_services(
    settings: AppSettings = Depends(get_settings),
) -> list[HealthStatus]:
    """Run all health checks and return service statuses.

    Creates a temporary ``HealthService`` instance, runs checks, closes it.
    """
    svc = HealthService(settings.service)
    try:
        return await svc.check_all()
    finally:
        await svc.close()
