"""Universe endpoints — stats and refresh."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from options_arena.api.deps import get_universe
from options_arena.api.schemas import UniverseStats
from options_arena.services import UniverseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["universe"])


@router.get("/universe")
async def get_universe_stats(
    universe: UniverseService = Depends(get_universe),
) -> UniverseStats:
    """Get universe statistics."""
    optionable = await universe.fetch_optionable_tickers()
    sp500 = await universe.fetch_sp500_constituents()
    return UniverseStats(
        optionable_count=len(optionable),
        sp500_count=len(sp500),
    )


@router.post("/universe/refresh")
async def refresh_universe(
    universe: UniverseService = Depends(get_universe),
) -> UniverseStats:
    """Trigger a refresh of the universe data and return updated stats."""
    # Invalidate cache by fetching fresh
    optionable = await universe.fetch_optionable_tickers()
    sp500 = await universe.fetch_sp500_constituents()
    return UniverseStats(
        optionable_count=len(optionable),
        sp500_count=len(sp500),
    )
