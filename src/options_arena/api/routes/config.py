"""Read-only config endpoint — safe values only (no secrets)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_settings
from options_arena.api.schemas import ConfigResponse
from options_arena.models import AppSettings

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
@limiter.limit("60/minute")
async def get_config(
    request: Request,
    settings: AppSettings = Depends(get_settings),
) -> ConfigResponse:
    """Return safe configuration values (never the actual API key)."""
    has_api_key = settings.debate.api_key is not None or os.environ.get("GROQ_API_KEY") is not None
    return ConfigResponse(
        groq_api_key_set=has_api_key,
        scan_preset_default="sp500",
        enable_rebuttal=settings.debate.enable_rebuttal,
        enable_volatility_agent=settings.debate.enable_volatility_agent,
        agent_timeout=settings.debate.agent_timeout,
    )
