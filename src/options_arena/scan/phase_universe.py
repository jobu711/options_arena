"""Phase 1: Universe — fetch optionable tickers, S&P 500 sectors, and OHLCV data.

Extracted from ``ScanPipeline._phase_universe()`` as a standalone async function.
All service and config dependencies are passed as explicit parameters.
"""

from __future__ import annotations

import logging

from options_arena.data import Repository
from options_arena.models import (
    SECTOR_ALIASES,
    SECTOR_TO_INDUSTRY_GROUPS,
    GICSSector,
    MarketCapTier,
    ScanPreset,
)
from options_arena.models.filters import UniverseFilters
from options_arena.models.market_data import OHLCV
from options_arena.scan.models import UniverseResult
from options_arena.scan.progress import ProgressCallback, ScanPhase
from options_arena.services import MarketDataService, UniverseService, build_industry_group_map

# Use pipeline logger name so that tests filtering on "options_arena.scan.pipeline"
# continue to capture phase log messages after extraction.
logger = logging.getLogger("options_arena.scan.pipeline")


async def run_universe_phase(
    progress: ProgressCallback,
    *,
    universe: UniverseService,
    market_data: MarketDataService,
    repository: Repository,
    universe_filters: UniverseFilters,
) -> UniverseResult:
    """Phase 1: Fetch optionable universe and OHLCV data.

    Steps:
        1. Fetch optionable tickers from CBOE.
        2. Fetch S&P 500 constituents and build sector dict.
        3. If preset is SP500, filter tickers to S&P 500 only.
        4. Batch-fetch OHLCV for all tickers.
        5. Filter by minimum bar count (``ohlcv_min_bars``).
        6. Report progress.

    Args:
        progress: Callback for reporting per-phase progress.
        universe: Universe service for optionable tickers and S&P 500 data.
        market_data: Market data service for OHLCV fetching.
        repository: Data layer for metadata enrichment.
        universe_filters: Universe selection filters (preset, sectors, custom tickers, etc.).

    Returns:
        ``UniverseResult`` with tickers, OHLCV map, sectors, and counts.
    """
    # Step 1: Fetch optionable tickers
    all_tickers = await universe.fetch_optionable_tickers()
    logger.info("Universe: %d optionable tickers fetched", len(all_tickers))

    # Step 2: Fetch S&P 500 constituents and build typed sector_map
    sp500_constituents = await universe.fetch_sp500_constituents()
    sp500_sectors: dict[str, str] = {c.ticker: c.sector for c in sp500_constituents}
    logger.info("S&P 500: %d constituents fetched", len(sp500_sectors))

    # Build typed sector_map from raw sector strings via SECTOR_ALIASES
    sector_map: dict[str, GICSSector] = {}
    for ticker, raw_sector in sp500_sectors.items():
        key = raw_sector.strip().lower()
        gics = SECTOR_ALIASES.get(key)
        if gics is not None:
            sector_map[ticker] = gics
        else:
            # Try direct enum construction for canonical values
            try:
                sector_map[ticker] = GICSSector(raw_sector.strip())
            except ValueError:
                logger.debug(
                    "Unknown sector %r for %s; skipping sector assignment",
                    raw_sector,
                    ticker,
                )
    logger.info("Sector map: %d tickers mapped to GICS sectors", len(sector_map))

    # Step 3: Build industry group map from GICS Sub-Industry (CSV data)
    sub_industry_data: dict[str, str] = {
        c.ticker: c.sub_industry for c in sp500_constituents if c.sub_industry
    }
    industry_group_map = build_industry_group_map(sub_industry_data)
    from_sub = len(industry_group_map)

    # Fallback: infer from sector for tickers without sub-industry data
    for ticker, sector in sector_map.items():
        if ticker not in industry_group_map:
            groups = SECTOR_TO_INDUSTRY_GROUPS.get(sector, [])
            if len(groups) == 1:
                industry_group_map[ticker] = groups[0]
    logger.info(
        "Industry group map: %d tickers (%d from sub-industry, %d inferred)",
        len(industry_group_map),
        from_sub,
        len(industry_group_map) - from_sub,
    )

    # Step 4 (metadata enrichment): load cached metadata to extend maps beyond S&P 500
    try:
        all_metadata = await repository.get_all_ticker_metadata()
        for meta in all_metadata:
            if meta.ticker not in sector_map and meta.sector is not None:
                sector_map[meta.ticker] = meta.sector
            if meta.ticker not in industry_group_map and meta.industry_group is not None:
                industry_group_map[meta.ticker] = meta.industry_group
        logger.info(
            "Metadata enrichment: sector_map=%d, industry_group_map=%d",
            len(sector_map),
            len(industry_group_map),
        )
    except Exception:
        logger.warning(
            "Failed to load ticker metadata, continuing without enrichment",
            exc_info=True,
        )
        all_metadata = []

    # Step 4a: Market cap pre-filter — before OHLCV fetch (saves expensive API calls)
    if universe_filters.market_cap_tiers:
        metadata_by_ticker: dict[str, MarketCapTier | None] = {
            m.ticker: m.market_cap_tier for m in all_metadata
        }
        if metadata_by_ticker:
            allowed_tiers = frozenset(universe_filters.market_cap_tiers)
            before_count = len(all_tickers)
            all_tickers = [
                t
                for t in all_tickers
                if t not in metadata_by_ticker  # keep tickers without metadata
                or metadata_by_ticker[t] in allowed_tiers
            ]
            logger.info(
                "Market cap filter (%s): %d -> %d tickers",
                [t.value for t in universe_filters.market_cap_tiers],
                before_count,
                len(all_tickers),
            )
        else:
            logger.warning(
                "Market cap tiers requested but metadata cache is empty; skipping filter"
            )

    # Step 3a: Custom tickers branch — bypass preset/sector/industry filters
    custom = universe_filters.custom_tickers
    tickers: list[str]
    if custom:
        optionable_set = frozenset(all_tickers)
        valid = [t for t in custom if t in optionable_set]
        excluded = [t for t in custom if t not in optionable_set]
        if excluded:
            logger.warning("Custom tickers not in optionable universe: %s", excluded)
        logger.info("Custom tickers: %d requested, %d valid", len(custom), len(valid))
        tickers = valid
    else:
        # Preset filter
        preset = universe_filters.preset
        if preset == ScanPreset.SP500:
            sp500_set = set(sp500_sectors.keys())
            tickers = [t for t in all_tickers if t in sp500_set]
            logger.info(
                "SP500 preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        elif preset == ScanPreset.ETFS:
            etf_tickers = await universe.fetch_etf_tickers()
            etf_set = frozenset(etf_tickers)
            tickers = [t for t in all_tickers if t in etf_set]
            logger.info(
                "ETFS preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        elif preset == ScanPreset.NASDAQ100:
            preset_tickers = await universe.fetch_nasdaq100_constituents()
            preset_set = frozenset(preset_tickers)
            tickers = [t for t in all_tickers if t in preset_set]
            logger.info(
                "NASDAQ100 preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        elif preset == ScanPreset.RUSSELL2000:
            preset_tickers = await universe.fetch_russell2000_tickers(
                repo=repository,
            )
            preset_set = frozenset(preset_tickers)
            tickers = [t for t in all_tickers if t in preset_set]
            logger.info(
                "RUSSELL2000 preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        elif preset == ScanPreset.MOST_ACTIVE:
            preset_tickers = await universe.fetch_most_active()
            preset_set = frozenset(preset_tickers)
            tickers = [t for t in all_tickers if t in preset_set]
            logger.info(
                "MOST_ACTIVE preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        else:
            tickers = all_tickers

        # Sector filter (OR logic) when sectors are configured
        configured_sectors = universe_filters.sectors
        if configured_sectors:
            sector_set = frozenset(configured_sectors)
            before_count = len(tickers)
            tickers = [t for t in tickers if sector_map.get(t) in sector_set]
            logger.info(
                "Sector filter: %d -> %d tickers (sectors=%s)",
                before_count,
                len(tickers),
                ", ".join(s.value for s in configured_sectors),
            )

        # Warn if industry group map coverage is low relative to active tickers
        if industry_group_map and tickers:
            ig_coverage = sum(1 for t in tickers if t in industry_group_map) / len(tickers)
            if ig_coverage < 0.5:
                logger.warning(
                    "Industry group map covers only %.0f%% of %d active tickers; "
                    "industry group filtering may exclude valid tickers",
                    ig_coverage * 100,
                    len(tickers),
                )

        # Industry group filter (OR logic) when configured
        configured_industry_groups = universe_filters.industry_groups
        if configured_industry_groups:
            ig_set = frozenset(configured_industry_groups)
            before_count = len(tickers)
            tickers = [t for t in tickers if industry_group_map.get(t) in ig_set]
            logger.info(
                "Industry group filter: %d -> %d tickers (groups=%s)",
                before_count,
                len(tickers),
                ", ".join(ig.value for ig in configured_industry_groups),
            )

    # Step 4: Batch-fetch OHLCV
    progress(ScanPhase.UNIVERSE, 0, len(tickers))
    batch_result = await market_data.fetch_batch_ohlcv(tickers, period="1y")

    # Step 5: Filter by minimum bar count
    min_bars = universe_filters.ohlcv_min_bars
    ohlcv_map: dict[str, list[OHLCV]] = {}
    failed_count = 0
    filtered_count = 0

    for result in batch_result.results:
        if not result.ok or result.data is None:
            failed_count += 1
            continue

        if len(result.data) < min_bars:
            filtered_count += 1
            logger.info(
                "Filtered %s: %d bars < minimum %d",
                result.ticker,
                len(result.data),
                min_bars,
            )
            continue

        ohlcv_map[result.ticker] = result.data

    logger.info(
        "Universe phase complete: %d tickers with data, %d failed, %d filtered",
        len(ohlcv_map),
        failed_count,
        filtered_count,
    )

    # Step 6: Report progress
    progress(ScanPhase.UNIVERSE, len(tickers), len(tickers))

    return UniverseResult(
        tickers=tickers,
        ohlcv_map=ohlcv_map,
        sp500_sectors=sp500_sectors,
        sector_map=sector_map,
        industry_group_map=industry_group_map,
        failed_count=failed_count,
        filtered_count=filtered_count,
    )
