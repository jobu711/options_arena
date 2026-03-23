"""Universe endpoints — stats, sector hierarchy, and preset-info."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from fastapi import APIRouter, Depends, Request

from options_arena.api.app import limiter
from options_arena.api.deps import (
    get_repo,
    get_universe,
)
from options_arena.api.schemas import (
    IndustryGroupInfo,
    PresetInfo,
    SectorHierarchy,
    UniverseStats,
)
from options_arena.data import Repository
from options_arena.models.enums import (
    SECTOR_TO_INDUSTRY_GROUPS,
    GICSIndustryGroup,
    GICSSector,
    ScanPreset,
)
from options_arena.services import UniverseService
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


# ---------------------------------------------------------------------------
# Preset info endpoint (#286)
# ---------------------------------------------------------------------------


@router.get("/universe/preset-info")
@limiter.limit("60/minute")
async def get_preset_info(
    request: Request,
    universe: UniverseService = Depends(get_universe),
    repo: Repository = Depends(get_repo),
) -> list[PresetInfo]:
    """Return metadata for all 6 scan presets with estimated ticker counts.

    Uses ``asyncio.gather`` to fetch all preset universes in parallel,
    then builds a ``PresetInfo`` response for each preset.
    """
    # Fetch all 6 preset universes in parallel
    (
        optionable_result,
        sp500_result,
        etf_result,
        nasdaq100_result,
        russell2000_result,
        most_active_result,
    ) = await asyncio.gather(
        universe.fetch_optionable_tickers(),
        universe.fetch_sp500_constituents(),
        universe.fetch_etf_tickers(),
        universe.fetch_nasdaq100_constituents(),
        universe.fetch_russell2000_tickers(repo=repo),
        universe.fetch_most_active(),
        return_exceptions=True,
    )

    # Safe count extraction — if a fetch raised, count is 0
    def _safe_len(result: object) -> int:
        if isinstance(result, BaseException):
            logger.warning("Preset fetch failed: %s", result)
            return 0
        if isinstance(result, list):
            return len(result)
        return 0

    return [
        PresetInfo(
            preset=ScanPreset.FULL,
            label="Full Universe",
            description="All CBOE optionable equities and ETFs.",
            estimated_count=_safe_len(optionable_result),
        ),
        PresetInfo(
            preset=ScanPreset.SP500,
            label="S&P 500",
            description="Large-cap U.S. equities in the S&P 500 index.",
            estimated_count=_safe_len(sp500_result),
        ),
        PresetInfo(
            preset=ScanPreset.ETFS,
            label="ETFs",
            description="Exchange-traded funds with liquid options markets.",
            estimated_count=_safe_len(etf_result),
        ),
        PresetInfo(
            preset=ScanPreset.NASDAQ100,
            label="Nasdaq 100",
            description="Top 100 non-financial companies on the Nasdaq exchange.",
            estimated_count=_safe_len(nasdaq100_result),
        ),
        PresetInfo(
            preset=ScanPreset.RUSSELL2000,
            label="Russell 2000",
            description="Small-cap and micro-cap equities with options.",
            estimated_count=_safe_len(russell2000_result),
        ),
        PresetInfo(
            preset=ScanPreset.MOST_ACTIVE,
            label="Most Active",
            description="Most actively traded options by volume.",
            estimated_count=_safe_len(most_active_result),
        ),
    ]
