"""Universe endpoints — stats, refresh, sector hierarchy, and themes."""

from __future__ import annotations

import logging
from collections import Counter

from fastapi import APIRouter, Depends, Request

from options_arena.api.app import limiter
from options_arena.api.deps import get_theme_service, get_universe
from options_arena.api.schemas import (
    IndustryGroupInfo,
    SectorHierarchy,
    ThemeInfo,
    UniverseStats,
)
from options_arena.models.enums import SECTOR_TO_INDUSTRY_GROUPS, GICSIndustryGroup, GICSSector
from options_arena.services import UniverseService
from options_arena.services.theme_service import ThemeService
from options_arena.services.universe import build_sector_map

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["universe"])


@router.get("/universe")
@limiter.limit("60/minute")
async def get_universe_stats(
    request: Request,
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
@limiter.limit("60/minute")
async def refresh_universe(
    request: Request,
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
@limiter.limit("60/minute")
async def get_sectors(
    request: Request,
    universe: UniverseService = Depends(get_universe),
) -> list[SectorHierarchy]:
    """Return GICS sectors with nested industry groups and ticker counts.

    Returns a hierarchical structure: each sector contains its child
    industry groups, both with accurate ticker counts derived from
    S&P 500 constituents. Industry group counts are inferred from sectors
    with a single child group; multi-group sectors show 0 per group
    (full resolution requires yfinance industry data).
    """
    constituents = await universe.fetch_sp500_constituents()
    sector_map = build_sector_map(constituents)

    # Count tickers per sector
    sector_counts: Counter[GICSSector] = Counter()
    for sector in sector_map.values():
        sector_counts[sector] += 1

    # Infer industry group counts: for sectors with exactly one industry
    # group, all tickers in that sector belong to that group.
    ig_counts: Counter[GICSIndustryGroup] = Counter()
    for sector, count in sector_counts.items():
        groups = SECTOR_TO_INDUSTRY_GROUPS.get(sector, [])
        if len(groups) == 1:
            ig_counts[groups[0]] += count

    # Build hierarchical response using SECTOR_TO_INDUSTRY_GROUPS mapping
    hierarchy: list[SectorHierarchy] = []
    for sector in sorted(GICSSector, key=lambda s: s.value):
        child_groups = SECTOR_TO_INDUSTRY_GROUPS.get(sector, [])
        ig_infos = [
            IndustryGroupInfo(
                name=ig.value,
                ticker_count=ig_counts.get(ig, 0),
            )
            for ig in child_groups
        ]

        hierarchy.append(
            SectorHierarchy(
                name=sector.value,
                ticker_count=sector_counts.get(sector, 0),
                industry_groups=ig_infos,
            )
        )

    return hierarchy


@router.get("/themes")
@limiter.limit("60/minute")
async def get_themes(
    request: Request,
    theme_service: ThemeService = Depends(get_theme_service),
) -> list[ThemeInfo]:
    """Return available investment themes with ticker counts and source ETFs."""
    snapshots = await theme_service.get_themes()
    return [
        ThemeInfo(
            name=t.name,
            ticker_count=t.ticker_count,
            source_etfs=t.source_etfs,
        )
        for t in snapshots
    ]
