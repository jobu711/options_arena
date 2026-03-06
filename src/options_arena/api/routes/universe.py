"""Universe endpoints — stats, refresh, sector hierarchy, themes, and metadata index."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from options_arena.api.app import limiter
from options_arena.api.deps import (
    get_market_data,
    get_operation_lock,
    get_repo,
    get_theme_service,
    get_universe,
)
from options_arena.api.schemas import (
    IndexStarted,
    IndustryGroupInfo,
    MetadataStats,
    PresetInfo,
    SectorHierarchy,
    ThemeInfo,
    UniverseStats,
)
from options_arena.data import Repository
from options_arena.models.enums import (
    SECTOR_TO_INDUSTRY_GROUPS,
    GICSIndustryGroup,
    GICSSector,
    ScanPreset,
)
from options_arena.services import MarketDataService, UniverseService
from options_arena.services.theme_service import ThemeService
from options_arena.services.universe import build_sector_map, map_yfinance_to_metadata

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
        if isinstance(result, Exception):
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


# ---------------------------------------------------------------------------
# Metadata index endpoints (#274)
# ---------------------------------------------------------------------------


_INDEX_CONCURRENCY = 5


async def _run_index_background(
    task_id: int,
    force: bool,
    max_age: int,
    universe: UniverseService,
    market_data: MarketDataService,
    repo: Repository,
    lock: asyncio.Lock,
) -> None:
    """Run bulk metadata indexing as a background task.

    The lock is already acquired by the caller — this task releases it on completion.
    Uses a semaphore for concurrency control, matching the CLI implementation.
    """
    try:
        # 1. Get CBOE optionable ticker list
        all_tickers = await universe.fetch_optionable_tickers()

        # 2. Determine which tickers need indexing
        if force:
            tickers_to_index = all_tickers
        else:
            optionable_set = set(all_tickers)
            stale_set = set(await repo.get_stale_tickers(max_age_days=max_age)) & optionable_set
            # Also include tickers not yet in the metadata table
            existing_metadata = await repo.get_all_ticker_metadata()
            existing_set = {m.ticker for m in existing_metadata}
            new_tickers = [t for t in all_tickers if t not in existing_set]
            tickers_to_index = sorted(set(new_tickers) | stale_set)

        logger.info(
            "Metadata index task %d: indexing %d tickers (force=%s, max_age=%d)",
            task_id,
            len(tickers_to_index),
            force,
            max_age,
        )

        # 3. Process tickers with concurrency control
        sem = asyncio.Semaphore(_INDEX_CONCURRENCY)
        indexed = 0
        errors = 0

        async def _process_one(ticker: str) -> bool:
            async with sem:
                try:
                    ticker_info = await market_data.fetch_ticker_info(ticker)
                    metadata = map_yfinance_to_metadata(ticker_info)
                    await repo.upsert_ticker_metadata(metadata)
                    return True
                except Exception:
                    logger.debug("Failed to index metadata for %s", ticker, exc_info=True)
                    return False

        results = await asyncio.gather(
            *[_process_one(t) for t in tickers_to_index],
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, Exception):
                errors += 1
                logger.warning("Unexpected gather error: %s", result)
            elif result:
                indexed += 1
            else:
                errors += 1

        logger.info(
            "Metadata index task %d complete: indexed=%d, errors=%d",
            task_id,
            indexed,
            errors,
        )
    except Exception:
        logger.exception("Metadata index task %d failed", task_id)
    finally:
        lock.release()


@router.get("/universe/metadata/stats")
@limiter.limit("60/minute")
async def get_metadata_stats(
    request: Request,
    repo: Repository = Depends(get_repo),
) -> MetadataStats:
    """Return metadata coverage statistics."""
    coverage = await repo.get_metadata_coverage()
    return MetadataStats(
        total=coverage.total,
        with_sector=coverage.with_sector,
        with_industry_group=coverage.with_industry_group,
        coverage=coverage.coverage,
    )


@router.post("/universe/index", status_code=202)
@limiter.limit("5/minute")
async def start_index(
    request: Request,
    force: bool = Query(False),
    max_age: int = Query(30, ge=1),
    lock: asyncio.Lock = Depends(get_operation_lock),
    universe: UniverseService = Depends(get_universe),
    market_data: MarketDataService = Depends(get_market_data),
    repo: Repository = Depends(get_repo),
) -> IndexStarted:
    """Trigger bulk metadata indexing as a background task.

    Acquires the operation lock. Returns 409 if another operation is in progress.
    """
    # Atomic try-acquire: eliminates TOCTOU race between lock.locked() and acquire()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=0.01)
    except TimeoutError:
        raise HTTPException(409, "Another operation is in progress") from None

    # Counter-based task ID
    request.app.state.index_counter += 1
    task_id: int = request.app.state.index_counter

    # Background task owns the lock and releases it on completion
    asyncio.create_task(
        _run_index_background(task_id, force, max_age, universe, market_data, repo, lock)
    )
    return IndexStarted(index_task_id=task_id)
