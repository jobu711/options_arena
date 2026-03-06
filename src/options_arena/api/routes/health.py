"""Health check endpoints — basic liveness + full service check."""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, Request

from options_arena.api.deps import get_operation_lock, get_settings
from options_arena.api.schemas import OperationStatus
from options_arena.models import AppSettings, HealthStatus
from options_arena.services.health import HealthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Basic liveness check."""
    return {"status": "ok"}


@router.get("/status")
async def get_status(
    request: Request,
    lock: asyncio.Lock = Depends(get_operation_lock),
) -> OperationStatus:
    """Return current operation status so frontend can sync after browser refresh."""
    active_scans: dict[int, object] = getattr(request.app.state, "active_scans", {})
    active_scan_ids = list(active_scans.keys())
    active_debates: dict[int, object] = getattr(request.app.state, "debate_queues", {})
    active_debate_ids = list(active_debates.keys())
    return OperationStatus(
        busy=lock.locked(),
        active_scan_ids=active_scan_ids,
        active_debate_ids=active_debate_ids,
    )


@router.get("/health/services")
async def check_services(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> list[HealthStatus]:
    """Run all health checks and return service statuses.

    Creates a temporary ``HealthService`` instance, runs checks, closes it.
    Uses app-scoped cache and limiter for the CBOE chains health probe.
    """
    svc = HealthService(
        settings.service,
        openbb_config=settings.openbb,
        cache=request.app.state.cache,
        limiter=request.app.state.limiter,
    )
    try:
        return await svc.check_all()
    finally:
        await svc.close()
