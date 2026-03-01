"""Universe endpoints — stats, refresh, and sector listing."""

from __future__ import annotations

import logging
from collections import Counter

from fastapi import APIRouter, Depends

from options_arena.api.deps import get_universe
from options_arena.api.schemas import SectorInfo, UniverseStats
from options_arena.services import UniverseService
from options_arena.services.universe import build_sector_map

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["universe"])


@router.get("/universe")
async def get_universe_stats(
    universe: UniverseService = Depends(get_universe),
) -> UniverseStats:
    """Get universe statistics including ETF count."""
    optionable = await universe.fetch_optionable_tickers()
    sp500 = await universe.fetch_sp500_constituents()
    etfs = await universe.fetch_etf_tickers()
    return UniverseStats(
        optionable_count=len(optionable),
        sp500_count=len(sp500),
        etf_count=len(etfs),
    )


@router.post("/universe/refresh")
async def refresh_universe(
    universe: UniverseService = Depends(get_universe),
) -> UniverseStats:
    """Trigger a refresh of the universe data and return updated stats."""
    # Invalidate cache by fetching fresh
    optionable = await universe.fetch_optionable_tickers()
    sp500 = await universe.fetch_sp500_constituents()
    etfs = await universe.fetch_etf_tickers()
    return UniverseStats(
        optionable_count=len(optionable),
        sp500_count=len(sp500),
        etf_count=len(etfs),
    )


@router.get("/universe/sectors")
async def get_sectors(
    universe: UniverseService = Depends(get_universe),
) -> list[SectorInfo]:
    """Return all GICS sectors with ticker counts from S&P 500 constituents."""
    constituents = await universe.fetch_sp500_constituents()
    sector_map = build_sector_map(constituents)

    # Count tickers per sector
    counts: Counter[str] = Counter()
    for sector in sector_map.values():
        counts[sector.value] += 1

    # Sort alphabetically by sector name
    return sorted(
        [SectorInfo(name=name, ticker_count=count) for name, count in counts.items()],
        key=lambda s: s.name,
    )
