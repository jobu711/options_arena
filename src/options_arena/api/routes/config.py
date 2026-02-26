"""Read-only config endpoint — safe values only (no secrets)."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends

from options_arena.api.deps import get_settings
from options_arena.api.schemas import ConfigResponse
from options_arena.models import AppSettings

router = APIRouter(prefix="/api", tags=["config"])


@router.get("/config")
async def get_config(
    settings: AppSettings = Depends(get_settings),
) -> ConfigResponse:
    """Return safe configuration values (never the actual API key)."""
    api_key = settings.debate.api_key or os.environ.get("GROQ_API_KEY")
    return ConfigResponse(
        groq_api_key_set=api_key is not None,
        scan_preset_default="sp500",
        enable_rebuttal=settings.debate.enable_rebuttal,
        enable_volatility_agent=settings.debate.enable_volatility_agent,
        agent_timeout=settings.debate.agent_timeout,
    )
