"""Scan pipeline orchestration — 4-phase async pipeline.

Ties together ``services/``, ``indicators/``, ``scoring/``, and ``data/``
into a testable, cancellable, progress-reporting pipeline.  Replaces v3's
monolithic 430-line ``cli.py`` scan function with a ``ScanPipeline`` class.
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from options_arena.data import Repository
from options_arena.indicators.options_specific import max_pain
from options_arena.models import (
    SECTOR_ALIASES,
    SECTOR_TO_INDUSTRY_GROUPS,
    AppSettings,
    GICSSector,
    IndicatorSignals,
    MarketRegime,
    NormalizationStats,
    OptionContract,
    OptionType,
    RecommendedContract,
    ScanPreset,
    ScanRun,
    ScanSource,
    SignalDirection,
    TickerScore,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    compute_indicators,
    compute_options_indicators,
    compute_phase3_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scan.models import (
    OptionsResult,
    ScanResult,
    ScoringResult,
    UniverseResult,
)
from options_arena.scan.progress import (
    CancellationToken,
    ProgressCallback,
    ScanPhase,
)
from options_arena.scoring import (
    composite_score,
    compute_dimensional_scores,
    compute_direction_signal,
    compute_normalization_stats,
    determine_direction,
    percentile_rank_normalize,
    recommend_contracts,
    score_universe,
)
from options_arena.services import (
    FredService,
    MarketDataService,
    OptionsDataService,
    UniverseService,
    build_industry_group_map,
)
from options_arena.services.universe import map_yfinance_to_metadata

logger = logging.getLogger(__name__)


class ScanPipeline:
    """Four-phase async scan pipeline with cancellation and progress reporting.

    Services are injected via constructor (DI pattern).  The pipeline never
    creates, configures, or closes services -- that is the caller's
    responsibility (typically ``cli.py``).

    Args:
        settings: Full application settings (pipeline extracts scan/pricing slices).
        market_data: Market data service for OHLCV fetching.
        options_data: Options data service for chain fetching (Phase 3).
        fred: FRED service for risk-free rate (Phase 3).
        universe: Universe service for optionable tickers and S&P 500 data.
        repository: Data layer for persisting scan results (Phase 4).
    """

    def __init__(
        self,
        settings: AppSettings,
        market_data: MarketDataService,
        options_data: OptionsDataService,
        fred: FredService,
        universe: UniverseService,
        repository: Repository,
    ) -> None:
        self._settings = settings
        self._market_data = market_data
        self._options_data = options_data
        self._fred = fred
        self._universe = universe
        self._repository = repository

    async def run(
        self,
        preset: ScanPreset,
        token: CancellationToken,
        progress: ProgressCallback,
        source: ScanSource = ScanSource.MANUAL,
    ) -> ScanResult:
        """Orchestrate all pipeline phases with cancellation checks between phases.

        Args:
            preset: Universe preset (FULL, SP500, ETFS).
            token: Instance-scoped cancellation token checked between phases.
            progress: Callback for reporting per-phase progress.
            source: Origin of the scan (manual).

        Returns:
            A ``ScanResult`` with all phases completed (or partial if cancelled).
        """
        started_at = datetime.now(UTC)
        phases_completed = 0

        # Phase 1: Universe + OHLCV
        universe_result = await self._phase_universe(preset, progress)
        phases_completed = 1
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
                preset=preset,
                source=source,
                universe_result=universe_result,
                phases_completed=phases_completed,
            )

        # Phase 2: Indicators + Scoring + Direction
        scoring_result = await self._phase_scoring(universe_result, progress)
        phases_completed = 2
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
                preset=preset,
                source=source,
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
            )

        # Post-Phase 2: Apply direction filter if configured
        direction_filter = self._settings.scan.direction_filter
        if direction_filter is not None:
            before_count = len(scoring_result.scores)
            scoring_result.scores = [
                ts for ts in scoring_result.scores if ts.direction == direction_filter
            ]
            logger.info(
                "Direction filter (%s): %d -> %d tickers",
                direction_filter.value,
                before_count,
                len(scoring_result.scores),
            )

        # Phase 3: Liquidity Pre-filter + Options + Contracts
        options_result = await self._phase_options(scoring_result, universe_result, progress)

        # Populate next_earnings on TickerScore objects from Phase 3 earnings data
        for ts in scoring_result.scores:
            earnings = options_result.earnings_dates.get(ts.ticker)
            if earnings is not None:
                ts.next_earnings = earnings

        phases_completed = 3
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
                preset=preset,
                source=source,
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
                options_result=options_result,
            )

        # Phase 4: Persist
        return await self._phase_persist(
            started_at=started_at,
            preset=preset,
            source=source,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=progress,
        )

    async def _phase_universe(
        self,
        preset: ScanPreset,
        progress: ProgressCallback,
    ) -> UniverseResult:
        """Phase 1: Fetch universe tickers, S&P 500 sectors, and OHLCV data.

        Steps:
            1. Fetch optionable tickers from CBOE.
            2. Fetch S&P 500 constituents and build sector dict.
            3. If preset is SP500, filter tickers to S&P 500 only.
            4. Batch-fetch OHLCV for all tickers.
            5. Filter by minimum bar count (``ohlcv_min_bars``).
            6. Report progress.

        Returns:
            ``UniverseResult`` with tickers, OHLCV map, sectors, and counts.
        """
        # Step 1: Fetch optionable tickers
        all_tickers = await self._universe.fetch_optionable_tickers()
        logger.info("Universe: %d optionable tickers fetched", len(all_tickers))

        # Step 2: Fetch S&P 500 constituents and build typed sector_map
        sp500_constituents = await self._universe.fetch_sp500_constituents()
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
            all_metadata = await self._repository.get_all_ticker_metadata()
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

        # Step 3a: Custom tickers branch — bypass preset/sector/industry filters
        custom = self._settings.scan.custom_tickers
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
            if preset == ScanPreset.SP500:
                sp500_set = set(sp500_sectors.keys())
                tickers = [t for t in all_tickers if t in sp500_set]
                logger.info(
                    "SP500 preset: filtered %d -> %d tickers",
                    len(all_tickers),
                    len(tickers),
                )
            elif preset == ScanPreset.ETFS:
                etf_tickers = await self._universe.fetch_etf_tickers()
                etf_set = frozenset(etf_tickers)
                tickers = [t for t in all_tickers if t in etf_set]
                logger.info(
                    "ETFS preset: filtered %d -> %d tickers",
                    len(all_tickers),
                    len(tickers),
                )
            elif preset == ScanPreset.NASDAQ100:
                preset_tickers = await self._universe.fetch_nasdaq100_constituents()
                preset_set = frozenset(preset_tickers)
                tickers = [t for t in all_tickers if t in preset_set]
                logger.info(
                    "NASDAQ100 preset: filtered %d -> %d tickers",
                    len(all_tickers),
                    len(tickers),
                )
            elif preset == ScanPreset.RUSSELL2000:
                preset_tickers = await self._universe.fetch_russell2000_tickers(
                    repo=self._repository,
                )
                preset_set = frozenset(preset_tickers)
                tickers = [t for t in all_tickers if t in preset_set]
                logger.info(
                    "RUSSELL2000 preset: filtered %d -> %d tickers",
                    len(all_tickers),
                    len(tickers),
                )
            elif preset == ScanPreset.MOST_ACTIVE:
                preset_tickers = await self._universe.fetch_most_active()
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
            configured_sectors = self._settings.scan.sectors
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
            configured_industry_groups = self._settings.scan.industry_groups
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
        batch_result = await self._market_data.fetch_batch_ohlcv(tickers, period="1y")

        # Step 5: Filter by minimum bar count
        min_bars = self._settings.scan.ohlcv_min_bars
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

    async def _phase_scoring(
        self,
        universe_result: UniverseResult,
        progress: ProgressCallback,
    ) -> ScoringResult:
        """Phase 2: Compute indicators, score universe, classify direction.

        Steps:
            1. For each ticker, convert OHLCV to DataFrame and compute indicators.
            2. Score universe (percentile-rank normalize, composite score).
            3. Classify direction using RAW indicator values (not normalized).
            4. Report progress.

        CRITICAL: ``determine_direction()`` uses **raw** ADX/RSI/SMA values.
        Passing normalized (0--100 percentile) values to absolute thresholds
        (ADX < 15.0) produces meaningless results.

        Returns:
            ``ScoringResult`` with scored tickers and raw signals retained.
        """
        progress(ScanPhase.SCORING, 0, len(universe_result.ohlcv_map))

        # Step 1: Compute indicators for each ticker
        raw_signals: dict[str, IndicatorSignals] = {}
        for i, (ticker, ohlcv_list) in enumerate(universe_result.ohlcv_map.items()):
            df = ohlcv_to_dataframe(ohlcv_list)
            raw_signals[ticker] = compute_indicators(df, INDICATOR_REGISTRY)
            # Yield to event loop periodically to avoid blocking on large universes
            if i % 100 == 99:
                await asyncio.sleep(0)

        logger.info("Computed indicators for %d tickers", len(raw_signals))

        # Log per-indicator success rates for diagnostics
        if raw_signals:
            indicator_fields = [spec.field_name for spec in INDICATOR_REGISTRY]
            total = len(raw_signals)
            for field_name in indicator_fields:
                populated = sum(
                    1 for s in raw_signals.values() if getattr(s, field_name) is not None
                )
                rate = populated / total * 100.0
                if rate < 80.0:
                    logger.warning(
                        "Indicator %s success rate: %.0f%% (%d/%d)",
                        field_name,
                        rate,
                        populated,
                        total,
                    )

        # Step 2: Score universe (returns normalized signals on TickerScore)
        scored: list[TickerScore] = score_universe(raw_signals)

        # Step 3: Classify direction using RAW values (not normalized)
        # and enrich with sector from Phase 1 sector_map
        scan_config = self._settings.scan
        for ts in scored:
            raw = raw_signals[ts.ticker]
            ts.direction = determine_direction(
                adx=raw.adx or 0.0,
                rsi=raw.rsi or 50.0,
                sma_alignment=raw.sma_alignment or 0.0,
                config=scan_config,
                supertrend=raw.supertrend,
                roc=raw.roc,
            )
            sector = universe_result.sector_map.get(ts.ticker)
            if sector is not None:
                ts.sector = sector
            ig = universe_result.industry_group_map.get(ts.ticker)
            if ig is not None:
                ts.industry_group = ig

        # Step 3b: Compute dimensional scores, direction confidence, and market regime
        for ts in scored:
            try:
                dim_scores = compute_dimensional_scores(ts.signals)
                ts.dimensional_scores = dim_scores

                direction_signal = compute_direction_signal(
                    ts.signals,
                    ts.direction,
                )
                ts.direction_confidence = direction_signal.confidence
            except Exception:
                logger.warning(
                    "Dimensional scoring failed for %s; skipping",
                    ts.ticker,
                    exc_info=True,
                )

        logger.info(
            "Scoring phase complete: %d tickers scored, classified, and dimensionally scored",
            len(scored),
        )

        # Step 3c: Compute normalization distribution metadata from raw signals
        norm_stats = compute_normalization_stats(raw_signals)
        logger.info("Computed normalization stats for %d indicators", len(norm_stats))

        # Step 4: Report progress
        progress(ScanPhase.SCORING, len(universe_result.ohlcv_map), len(universe_result.ohlcv_map))

        return ScoringResult(
            scores=scored,
            raw_signals=raw_signals,
            normalization_stats=norm_stats,
        )

    async def _phase_options(
        self,
        scoring_result: ScoringResult,
        universe_result: UniverseResult,
        progress: ProgressCallback,
    ) -> OptionsResult:
        """Phase 3: Liquidity pre-filter, top-N selection, options + contracts.

        Steps:
            1. Apply liquidity pre-filter using OHLCV data from Phase 1.
            2. Take top-N tickers by composite_score.
            3. Fetch risk-free rate from FRED (once for entire scan).
            4. For each top-N ticker, concurrently fetch chains + ticker info,
               then call ``recommend_contracts()`` for 0 or 1 recommendations.
            5. Report progress.

        Per-ticker errors are isolated -- one failed ticker never crashes the scan.

        Returns:
            ``OptionsResult`` with recommendations and risk-free rate.
        """
        ohlcv_map = universe_result.ohlcv_map

        # Step 1: Liquidity pre-filter
        min_dollar_volume = self._settings.scan.min_dollar_volume
        min_price = self._settings.scan.min_price
        max_price = self._settings.scan.max_price

        liquid_scores: list[TickerScore] = []
        for ts in scoring_result.scores:
            ohlcv_list = ohlcv_map.get(ts.ticker)
            if ohlcv_list is None or len(ohlcv_list) == 0:
                continue

            avg_dollar_volume = sum(float(o.close) * o.volume for o in ohlcv_list) / len(
                ohlcv_list
            )
            latest_close = float(ohlcv_list[-1].close)

            if avg_dollar_volume < min_dollar_volume:
                continue
            if latest_close < min_price:
                continue
            if max_price is not None and latest_close > max_price:
                continue

            liquid_scores.append(ts)

        logger.info(
            "Liquidity pre-filter: %d -> %d tickers (min_dv=$%.0f, min_price=$%.0f%s)",
            len(scoring_result.scores),
            len(liquid_scores),
            min_dollar_volume,
            min_price,
            f", max_price=${max_price:.0f}" if max_price is not None else "",
        )

        # Step 2: Top-N selection (scores already sorted descending)
        top_n = self._settings.scan.top_n
        top_scores = liquid_scores[:top_n]

        logger.info("Top-N selection: %d tickers (top_n=%d)", len(top_scores), top_n)

        # Step 3: Fetch risk-free rate (once for entire scan, never raises)
        risk_free_rate: float = await self._fred.fetch_risk_free_rate()
        logger.info("Risk-free rate: %.4f", risk_free_rate)

        # Step 3b: Extract SPX close series for relative-strength indicators
        # SPX data may be available from Phase 1 OHLCV if "^GSPC" was in the universe,
        # otherwise we attempt a lightweight fetch. Failure is non-fatal.
        spx_close: pd.Series | None = None
        try:
            spx_ohlcv = ohlcv_map.get("^GSPC")
            if spx_ohlcv is not None and len(spx_ohlcv) >= 60:
                spx_df = ohlcv_to_dataframe(spx_ohlcv)
                spx_close = spx_df["close"]
                logger.info("SPX close series available from universe (%d bars)", len(spx_close))
            else:
                # Attempt lightweight fetch for SPX data
                try:
                    spx_batch = await self._market_data.fetch_batch_ohlcv(["^GSPC"], period="1y")
                    if (
                        spx_batch.results
                        and spx_batch.results[0].ok
                        and spx_batch.results[0].data is not None
                        and len(spx_batch.results[0].data) >= 60
                    ):
                        spx_df = ohlcv_to_dataframe(spx_batch.results[0].data)
                        spx_close = spx_df["close"]
                        logger.info("SPX close series fetched on-demand (%d bars)", len(spx_close))
                    else:
                        logger.debug(
                            "SPX fetch unavailable; relative strength indicators will be None"
                        )
                except Exception:
                    logger.warning(
                        "Failed to fetch SPX data; rs_vs_spx will be None", exc_info=True
                    )
        except Exception:
            logger.warning("Failed to extract SPX close series; rs_vs_spx will be None")

        # Step 4: Per-ticker options processing with semaphore-bounded concurrency
        # A semaphore limits concurrent chains-in-flight, allowing all tickers to
        # start immediately while preventing rate-limiter overload.
        progress(ScanPhase.OPTIONS, 0, len(top_scores))

        per_ticker_timeout = self._settings.scan.options_per_ticker_timeout
        concurrency = self._settings.scan.options_concurrency
        sem = asyncio.Semaphore(concurrency)
        recommendations: dict[str, list[OptionContract]] = {}
        earnings_dates: dict[str, date] = {}
        entry_prices: dict[str, Decimal] = {}
        completed = 0

        async def _fetch_with_sem(
            ts: TickerScore,
        ) -> tuple[str, list[OptionContract], date | None, Decimal | None]:
            nonlocal completed
            async with sem:
                try:
                    result = await asyncio.wait_for(
                        self._process_ticker_options(ts, risk_free_rate, ohlcv_map, spx_close),
                        timeout=per_ticker_timeout,
                    )
                    return result
                finally:
                    completed += 1
                    progress(ScanPhase.OPTIONS, completed, len(top_scores))

        all_results: list[
            tuple[str, list[OptionContract], date | None, Decimal | None] | BaseException
        ] = await asyncio.gather(
            *[_fetch_with_sem(ts) for ts in top_scores],
            return_exceptions=True,
        )

        for ts, result in zip(top_scores, all_results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "Options processing failed for %s: %s: %s",
                    ts.ticker,
                    type(result).__name__,
                    result,
                )
            else:
                ticker, contracts, next_earnings, entry_price = result
                if contracts:
                    recommendations[ticker] = contracts
                if next_earnings is not None:
                    earnings_dates[ticker] = next_earnings
                if entry_price is not None:
                    entry_prices[ticker] = entry_price

        logger.info(
            "Options phase complete: %d recommendations from %d tickers",
            len(recommendations),
            len(top_scores),
        )

        # Normalize Phase 3 fields (raw domain values → 0-100 percentile ranks)
        # so they are on the same scale as Phase 2 normalized fields.
        if len(top_scores) >= 2:
            _normalize_phase3_signals(top_scores)
            _recompute_composite_scores(top_scores)
            _recompute_dimensional_scores(top_scores)
        else:
            logger.info("Skipping Phase 3 re-score: need >=2 tickers for percentile normalization")

        progress(ScanPhase.OPTIONS, len(top_scores), len(top_scores))

        return OptionsResult(
            recommendations=recommendations,
            risk_free_rate=risk_free_rate,
            earnings_dates=earnings_dates,
            entry_prices=entry_prices,
        )

    async def _process_ticker_options(
        self,
        ticker_score: TickerScore,
        risk_free_rate: float,
        ohlcv_map: dict[str, list[OHLCV]],
        spx_close: pd.Series | None,
    ) -> tuple[str, list[OptionContract], date | None, Decimal | None]:
        """Fetch chains + ticker info + earnings date for a single ticker.

        Also computes Phase 3 DSE indicators (IV analytics, flow, fundamental,
        relative strength) from chain + ticker data and merges them into the
        ticker's ``IndicatorSignals``.

        Isolated per-ticker: exceptions propagate up to ``asyncio.gather``
        with ``return_exceptions=True``.

        Args:
            ticker_score: Scored ticker with direction set.
            risk_free_rate: Shared risk-free rate for this scan.
            ohlcv_map: Ticker to OHLCV bars from Phase 1 (for close/volume series).
            spx_close: SPX daily close prices for relative strength (None if unavailable).

        Returns:
            Tuple of (ticker, recommended contracts, next_earnings_date | None,
            entry_stock_price | None).
        """
        ticker = ticker_score.ticker

        # Fetch chains, ticker info, and earnings date concurrently
        chain_task = self._options_data.fetch_chain_all_expirations(ticker)
        info_task = self._market_data.fetch_ticker_info(ticker)
        earnings_task = self._market_data.fetch_earnings_date(ticker)

        chain_results, ticker_info, earnings_result = await asyncio.gather(
            chain_task, info_task, earnings_task, return_exceptions=True
        )

        # Re-raise required data failures
        if isinstance(chain_results, BaseException):
            raise chain_results
        if isinstance(ticker_info, BaseException):
            raise ticker_info

        # Earnings is optional — log and continue on failure
        earnings_date: date | None
        if isinstance(earnings_result, BaseException):
            logger.warning("Earnings fetch failed for %s: %s", ticker, earnings_result)
            earnings_date = None
        else:
            earnings_date = earnings_result

        # Pre-scan narrowing: check market cap tier + earnings proximity
        scan_config = self._settings.scan
        if (
            scan_config.market_cap_tiers
            and ticker_info.market_cap_tier is not None
            and ticker_info.market_cap_tier not in scan_config.market_cap_tiers
        ):
            logger.info(
                "Filtered %s: market_cap_tier %s not in %s",
                ticker,
                ticker_info.market_cap_tier.value,
                [t.value for t in scan_config.market_cap_tiers],
            )
            return (ticker, [], earnings_date, ticker_info.current_price)

        if scan_config.exclude_near_earnings_days is not None and earnings_date is not None:
            market_today = datetime.now(ZoneInfo("America/New_York")).date()
            days_to_earnings = (earnings_date - market_today).days
            if days_to_earnings < scan_config.exclude_near_earnings_days:
                logger.info(
                    "Filtered %s: earnings in %d days (< %d)",
                    ticker,
                    days_to_earnings,
                    scan_config.exclude_near_earnings_days,
                )
                return (ticker, [], earnings_date, ticker_info.current_price)

        # Enrich ticker_score with company_name from ticker info
        ticker_score.company_name = ticker_info.company_name

        # Write back metadata for this ticker
        try:
            metadata = map_yfinance_to_metadata(ticker_info)
            if ticker_score.sector is None and metadata.sector is not None:
                ticker_score.sector = metadata.sector
            if ticker_score.industry_group is None and metadata.industry_group is not None:
                ticker_score.industry_group = metadata.industry_group
            await self._repository.upsert_ticker_metadata(metadata)
        except Exception:
            logger.warning("Failed to upsert metadata for %s", ticker_info.ticker, exc_info=True)

        # Flatten all contracts across expirations
        all_contracts: list[OptionContract] = []
        for chain in chain_results:
            all_contracts.extend(chain.contracts)

        entry_stock_price = ticker_info.current_price

        if not all_contracts:
            logger.info("No contracts found for %s", ticker)
            return (ticker, [], earnings_date, entry_stock_price)

        spot = float(ticker_info.current_price)

        # Compute options-specific indicators from full chain before filtering
        options_signals = compute_options_indicators(all_contracts, spot)
        if options_signals.put_call_ratio is not None:
            ticker_score.signals.put_call_ratio = options_signals.put_call_ratio
        if options_signals.max_pain_distance is not None:
            ticker_score.signals.max_pain_distance = options_signals.max_pain_distance

        # Compute max_pain strike directly from chain for Phase 3 indicators
        mp_strike = _extract_mp_strike(all_contracts)

        # Compute Phase 3 DSE indicators (IV analytics, flow, fundamental, RS)
        ohlcv_list = ohlcv_map.get(ticker)
        if ohlcv_list is not None and len(ohlcv_list) > 0:
            try:
                ticker_df = ohlcv_to_dataframe(ohlcv_list)
                close_series: pd.Series = ticker_df["close"]

                dse_signals = compute_phase3_indicators(
                    contracts=all_contracts,
                    spot=spot,
                    close_series=close_series,
                    dividend_yield=ticker_info.dividend_yield,
                    next_earnings=earnings_date,
                    mp_strike=mp_strike,
                    spx_close=spx_close,
                )

                # Merge DSE signals into the ticker's existing signals
                _merge_signals(ticker_score.signals, dse_signals)

                logger.debug(
                    "Phase 3 DSE indicators computed for %s",
                    ticker,
                )
            except Exception:
                logger.warning(
                    "Phase 3 DSE indicators failed for %s; continuing with partial signals",
                    ticker,
                    exc_info=True,
                )

        # Pre-scan narrowing: IV rank filter (applied after Phase 3 DSE populates iv_rank)
        if scan_config.min_iv_rank is not None:
            iv_rank = ticker_score.signals.iv_rank
            if iv_rank is None or iv_rank < scan_config.min_iv_rank:
                logger.info(
                    "Filtered %s: iv_rank %s < min_iv_rank %.1f",
                    ticker,
                    iv_rank,
                    scan_config.min_iv_rank,
                )
                return (ticker, [], earnings_date, entry_stock_price)

        recommended = recommend_contracts(
            contracts=all_contracts,
            direction=ticker_score.direction,
            spot=spot,
            risk_free_rate=risk_free_rate,
            dividend_yield=ticker_info.dividend_yield,
            config=self._settings.pricing,
        )

        return (ticker, recommended, earnings_date, entry_stock_price)

    async def _phase_persist(
        self,
        *,
        started_at: datetime,
        preset: ScanPreset,
        source: ScanSource,
        universe_result: UniverseResult,
        scoring_result: ScoringResult,
        options_result: OptionsResult,
        progress: ProgressCallback,
    ) -> ScanResult:
        """Phase 4: Persist scan results to the database.

        Steps:
            1. Build ``ScanRun`` with UTC timestamps.
            2. Save scan run to get DB-assigned ID.
            3. Update each ``TickerScore.scan_run_id``.
            4. Batch-insert ticker scores.
            5. Report progress.
            6. Return final ``ScanResult``.

        Returns:
            ``ScanResult`` with all 4 phases completed and DB-assigned scan ID.
        """
        # Step 1: Build ScanRun
        recommendation_count = sum(
            len(contracts) for contracts in options_result.recommendations.values()
        )
        scan_run = ScanRun(
            started_at=started_at,
            completed_at=datetime.now(UTC),
            preset=preset,
            source=source,
            tickers_scanned=len(universe_result.tickers),
            tickers_scored=len(scoring_result.scores),
            recommendations=recommendation_count,
        )

        # Step 2: Save scan run → get DB-assigned ID
        # All Phase 4 saves use commit=False for atomic persistence;
        # a single commit() at the end ensures all-or-nothing semantics.
        scan_id: int = await self._repository.save_scan_run(scan_run, commit=False)
        logger.info("Persisted scan run id=%d", scan_id)

        # Step 3: Update scan_run_id on each TickerScore
        for ts in scoring_result.scores:
            ts.scan_run_id = scan_id

        # Step 4: Batch-insert ticker scores
        await self._repository.save_ticker_scores(scan_id, scoring_result.scores, commit=False)
        logger.info(
            "Persisted %d ticker scores for scan %d",
            len(scoring_result.scores),
            scan_id,
        )

        # Step 5: Build and persist RecommendedContract list
        now_utc = datetime.now(UTC)
        score_map: dict[str, TickerScore] = {ts.ticker: ts for ts in scoring_result.scores}
        recommended_contracts: list[RecommendedContract] = []
        for ticker, contracts in options_result.recommendations.items():
            entry_price = options_result.entry_prices.get(ticker)
            matched_score: TickerScore | None = score_map.get(ticker)
            for contract in contracts:
                entry_mid = contract.mid
                recommended_contracts.append(
                    RecommendedContract(
                        scan_run_id=scan_id,
                        ticker=contract.ticker,
                        option_type=contract.option_type,
                        strike=contract.strike,
                        expiration=contract.expiration,
                        bid=contract.bid,
                        ask=contract.ask,
                        last=contract.last,
                        volume=contract.volume,
                        open_interest=contract.open_interest,
                        market_iv=contract.market_iv,
                        exercise_style=contract.exercise_style,
                        delta=(contract.greeks.delta if contract.greeks is not None else None),
                        gamma=(contract.greeks.gamma if contract.greeks is not None else None),
                        theta=(contract.greeks.theta if contract.greeks is not None else None),
                        vega=(contract.greeks.vega if contract.greeks is not None else None),
                        rho=(contract.greeks.rho if contract.greeks is not None else None),
                        pricing_model=(
                            contract.greeks.pricing_model if contract.greeks is not None else None
                        ),
                        greeks_source=contract.greeks_source,
                        entry_stock_price=entry_price,
                        entry_mid=entry_mid,
                        direction=(
                            matched_score.direction
                            if matched_score is not None
                            else SignalDirection.NEUTRAL
                        ),
                        composite_score=(
                            matched_score.composite_score if matched_score is not None else 0.0
                        ),
                        risk_free_rate=options_result.risk_free_rate,
                        created_at=now_utc,
                    )
                )

        if recommended_contracts:
            await self._repository.save_recommended_contracts(
                scan_id, recommended_contracts, commit=False
            )
            logger.info(
                "Persisted %d recommended contracts for scan %d",
                len(recommended_contracts),
                scan_id,
            )

        # Step 6: Persist normalization stats with real scan_run_id
        # NormalizationStats is frozen, so rebuild with the correct scan_run_id.
        if scoring_result.normalization_stats:
            real_stats = [
                NormalizationStats(
                    scan_run_id=scan_id,
                    indicator_name=s.indicator_name,
                    ticker_count=s.ticker_count,
                    min_value=s.min_value,
                    max_value=s.max_value,
                    median_value=s.median_value,
                    mean_value=s.mean_value,
                    std_dev=s.std_dev,
                    p25=s.p25,
                    p75=s.p75,
                    created_at=s.created_at,
                )
                for s in scoring_result.normalization_stats
            ]
            await self._repository.save_normalization_stats(scan_id, real_stats, commit=False)
            logger.info(
                "Persisted %d normalization stats for scan %d",
                len(real_stats),
                scan_id,
            )

        # Step 7: Atomic commit — all Phase 4 writes succeed or fail together
        await self._repository.commit()

        # Step 8: Report progress
        progress(ScanPhase.PERSIST, 1, 1)

        # Step 9: Return final ScanResult
        # ScanRun is frozen — reconstruct with ID populated
        final_scan_run = ScanRun(
            id=scan_id,
            started_at=scan_run.started_at,
            completed_at=scan_run.completed_at,
            preset=scan_run.preset,
            source=scan_run.source,
            tickers_scanned=scan_run.tickers_scanned,
            tickers_scored=scan_run.tickers_scored,
            recommendations=scan_run.recommendations,
        )

        return ScanResult(
            scan_run=final_scan_run,
            scores=scoring_result.scores,
            recommendations=options_result.recommendations,
            risk_free_rate=options_result.risk_free_rate,
            earnings_dates=options_result.earnings_dates,
            phases_completed=4,
        )

    def _make_cancelled_result(
        self,
        *,
        started_at: datetime,
        preset: ScanPreset,
        source: ScanSource,
        universe_result: UniverseResult,
        phases_completed: int,
        scoring_result: ScoringResult | None = None,
        options_result: OptionsResult | None = None,
    ) -> ScanResult:
        """Build a partial ScanResult when the pipeline is cancelled.

        Args:
            started_at: Pipeline start time (UTC).
            preset: Scan preset used.
            universe_result: Phase 1 output.
            phases_completed: Number of phases completed before cancellation.
            scoring_result: Phase 2 output (None if cancelled after Phase 1).
            options_result: Phase 3 output (None if cancelled before Phase 3).

        Returns:
            A ``ScanResult`` with ``cancelled=True`` and partial data.
        """
        scores = scoring_result.scores if scoring_result is not None else []
        tickers_scored = len(scores)
        recommendations = options_result.recommendations if options_result is not None else {}
        recommendation_count = sum(len(c) for c in recommendations.values())
        risk_free_rate = (
            options_result.risk_free_rate
            if options_result is not None
            else self._settings.pricing.risk_free_rate_fallback
        )
        earnings_dates = options_result.earnings_dates if options_result is not None else {}

        logger.warning(
            "Scan cancelled after %d phases (%d tickers scanned, %d scored)",
            phases_completed,
            len(universe_result.tickers),
            tickers_scored,
        )

        return ScanResult(
            scan_run=ScanRun(
                started_at=started_at,
                completed_at=datetime.now(UTC),
                preset=preset,
                source=source,
                tickers_scanned=len(universe_result.tickers),
                tickers_scored=tickers_scored,
                recommendations=recommendation_count,
            ),
            scores=scores,
            recommendations=recommendations,
            risk_free_rate=risk_free_rate,
            earnings_dates=earnings_dates,
            cancelled=True,
            phases_completed=phases_completed,
        )


# DSE field names computed in Phase 3 and merged into TickerScore.signals.
# Also includes put_call_ratio and max_pain_distance (computed per-ticker in
# Phase 3 via compute_options_indicators, not Phase 2).
_PHASE3_FIELDS: tuple[str, ...] = (
    # Options-specific (per-ticker Phase 3)
    "put_call_ratio",
    "max_pain_distance",
    # IV Analytics
    "iv_hv_spread",
    "hv_20d",
    "iv_term_slope",
    "iv_term_shape",
    "put_skew_index",
    "call_skew_index",
    "skew_ratio",
    "vol_regime",
    "ewma_vol_forecast",
    "vol_cone_percentile",
    "vix_correlation",
    "expected_move",
    "expected_move_ratio",
    # Flow Analytics
    "gex",
    "oi_concentration",
    "unusual_activity_score",
    "max_pain_magnet",
    # Second-Order Greeks
    "vanna",
    "charm",
    "vomma",
    # Risk
    "pop",
    "optimal_dte_score",
    "spread_quality",
    "max_loss_ratio",
    # Fundamental
    "earnings_em_ratio",
    "days_to_earnings_impact",
    "short_interest_ratio",
    "div_ex_date_impact",
    "iv_crush_history",
    # Relative Strength & Regime
    "rs_vs_spx",
    "correlation_regime_shift",
    "market_regime",
    "vix_term_structure",
    "risk_on_off_score",
    "sector_relative_momentum",
    # Liquidity
    "chain_spread_pct",
    "chain_oi_depth",
)


def _extract_mp_strike(contracts: list[OptionContract]) -> float | None:
    """Extract the max-pain strike from an option chain.

    Reuses the max_pain indicator function from ``indicators.options_specific``
    to find the strike where total option holder pain is maximized (minimum
    payout to option holders).

    Returns ``None`` if the chain has no OI data or computation fails.
    """
    strike_oi: dict[float, tuple[int, int]] = {}
    for c in contracts:
        s = float(c.strike)
        call_oi, put_oi = strike_oi.get(s, (0, 0))
        if c.option_type == OptionType.CALL:
            call_oi += c.open_interest
        else:
            put_oi += c.open_interest
        strike_oi[s] = (call_oi, put_oi)

    if not strike_oi:
        return None

    total_oi = sum(co + po for co, po in strike_oi.values())
    if total_oi <= 0:
        return None

    try:
        sorted_strikes = sorted(strike_oi.keys())
        strikes_series = pd.Series(sorted_strikes, dtype=float)
        call_oi_series = pd.Series([strike_oi[s][0] for s in sorted_strikes], dtype=float)
        put_oi_series = pd.Series([strike_oi[s][1] for s in sorted_strikes], dtype=float)
        mp = max_pain(strikes_series, call_oi_series, put_oi_series)
        if math.isfinite(mp) and not np.isnan(mp):
            return float(mp)
    except Exception:
        logger.warning("max_pain strike extraction failed", exc_info=True)

    return None


def _merge_signals(
    target: IndicatorSignals,
    source: IndicatorSignals,
) -> None:
    """Merge non-None fields from *source* into *target*.

    Only DSE fields (Phase 3 indicators) are merged.  Original Phase 2 fields
    on *target* are never overwritten.  Mutates *target* in place.
    """
    for field_name in _PHASE3_FIELDS:
        value = getattr(source, field_name, None)
        if value is not None:
            setattr(target, field_name, value)


def _normalize_phase3_signals(
    top_scores: list[TickerScore],
) -> None:
    """Percentile-rank normalize Phase 3 fields across the top-N universe.

    Phase 3 indicators are computed per-ticker and produce RAW domain values
    (e.g., ``iv_hv_spread=0.15``, ``gex=50000``).  Phase 2 indicators on
    ``TickerScore.signals`` are already percentile-ranked 0--100.  Mixing
    scales breaks dimensional scoring.

    This function:
    1. Extracts Phase 3 fields into a sub-universe of ``IndicatorSignals``.
    2. Runs ``percentile_rank_normalize()`` on those fields only.
    3. Writes the normalized values back, overwriting raw Phase 3 values.

    Phase 2 fields are untouched because only Phase 3 fields are populated
    in the sub-universe (all others are ``None`` and excluded from ranking).

    Mutates ``top_scores`` in place.
    """
    if len(top_scores) < 2:
        return  # normalization needs >= 2 tickers to rank

    phase3_field_set = frozenset(_PHASE3_FIELDS)

    # Step 1: Extract Phase 3 fields into a sub-universe
    sub_universe: dict[str, IndicatorSignals] = {}
    for ts in top_scores:
        kwargs: dict[str, float | None] = {}
        for field_name in IndicatorSignals.model_fields:
            if field_name in phase3_field_set:
                kwargs[field_name] = getattr(ts.signals, field_name)
            else:
                kwargs[field_name] = None
        sub_universe[ts.ticker] = IndicatorSignals(**kwargs)

    # Step 2: Percentile-rank normalize across the top-N universe
    normalized = percentile_rank_normalize(sub_universe)

    # Step 3: Write normalized values back into each ticker's signals
    for ts in top_scores:
        norm_signals = normalized.get(ts.ticker)
        if norm_signals is None:
            continue
        for field_name in _PHASE3_FIELDS:
            norm_value: float | None = getattr(norm_signals, field_name)
            if norm_value is not None:
                setattr(ts.signals, field_name, norm_value)

    logger.info(
        "Phase 3 normalization complete: %d fields across %d tickers",
        len(_PHASE3_FIELDS),
        len(top_scores),
    )


def _recompute_composite_scores(
    top_scores: list[TickerScore],
) -> None:
    """Recompute composite scores after Phase 3 normalization.

    Phase 2 composite scores are computed with only 14 of 18 indicators
    (options-specific fields are ``None``).  After Phase 3 populates and
    normalizes ``put_call_ratio``, ``max_pain_distance``, ``iv_rank``, and
    ``iv_percentile``, the composite score should be recomputed so it
    reflects all 18 weighted indicators.

    Mutates ``top_scores`` in place.

    Note: Phase 3 fields are percentile-ranked but NOT inverted because none of
    them appear in ``INVERTED_INDICATORS`` (which only contains volatility-width
    Phase 2 fields).  The already-inverted Phase 2 fields on ``ts.signals`` are
    preserved as-is, so ``composite_score()`` receives correct values for all 18.
    """
    for ts in top_scores:
        try:
            ts.composite_score = composite_score(ts.signals)
        except Exception:
            logger.warning(
                "Composite recompute failed for %s; keeping Phase 2 score",
                ts.ticker,
                exc_info=True,
            )

    # Re-sort by updated composite score (descending)
    top_scores.sort(key=lambda ts: ts.composite_score, reverse=True)
    logger.info("Phase 3 composite recompute complete for %d tickers", len(top_scores))


# Regime classification thresholds (applied to raw market_regime signal, 0-100 scale).
# Not configurable — empirical thresholds for vol-cone-based regime detection.
_REGIME_CRISIS_THRESHOLD: float = 80.0
_REGIME_VOLATILE_THRESHOLD: float = 60.0
_REGIME_MEAN_REVERTING_THRESHOLD: float = 40.0


def _recompute_dimensional_scores(
    top_scores: list[TickerScore],
) -> None:
    """Refresh dimensional scores, direction confidence, and market regime after Phase 3.

    The Phase 2 computation only saw Phase 2 fields.  Now that Phase 3 fields
    (including ``market_regime`` from vol cone data) are also normalized 0--100,
    recomputing gives dimensional scoring the full picture.

    Mutates ``top_scores`` in place.
    """
    for ts in top_scores:
        try:
            dim_scores = compute_dimensional_scores(ts.signals)
            ts.dimensional_scores = dim_scores

            direction_signal = compute_direction_signal(
                ts.signals,
                ts.direction,
            )
            ts.direction_confidence = direction_signal.confidence

            # Derive market regime from signals.market_regime (computed in Phase 3)
            regime_val = ts.signals.market_regime
            if regime_val is not None and math.isfinite(regime_val):
                if regime_val >= _REGIME_CRISIS_THRESHOLD:
                    ts.market_regime = MarketRegime.CRISIS
                elif regime_val >= _REGIME_VOLATILE_THRESHOLD:
                    ts.market_regime = MarketRegime.VOLATILE
                elif regime_val >= _REGIME_MEAN_REVERTING_THRESHOLD:
                    ts.market_regime = MarketRegime.MEAN_REVERTING
                else:
                    ts.market_regime = MarketRegime.TRENDING
        except Exception:
            logger.warning(
                "Dimensional re-scoring failed for %s; keeping Phase 2 values",
                ts.ticker,
                exc_info=True,
            )
