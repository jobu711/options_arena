"""Scan pipeline orchestration — 4-phase async pipeline.

Ties together ``services/``, ``indicators/``, ``scoring/``, and ``data/``
into a testable, cancellable, progress-reporting pipeline.  Replaces v3's
monolithic 430-line ``cli.py`` scan function with a ``ScanPipeline`` class.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from options_arena.data import Repository
from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    OptionContract,
    ScanPreset,
    ScanRun,
    TickerScore,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    compute_indicators,
    compute_options_indicators,
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
from options_arena.scoring import determine_direction, recommend_contracts, score_universe
from options_arena.services import (
    FredService,
    MarketDataService,
    OptionsDataService,
    UniverseService,
)

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
        watchlist_tickers: list[str] | None = None,
    ) -> ScanResult:
        """Orchestrate all pipeline phases with cancellation checks between phases.

        Args:
            preset: Universe preset (FULL, SP500, ETFS).
            token: Instance-scoped cancellation token checked between phases.
            progress: Callback for reporting per-phase progress.
            watchlist_tickers: Override universe with a specific ticker list (watchlist mode).

        Returns:
            A ``ScanResult`` with all phases completed (or partial if cancelled).
        """
        started_at = datetime.now(UTC)
        phases_completed = 0

        # Phase 1: Universe + OHLCV
        universe_result = await self._phase_universe(
            preset, progress, watchlist_tickers=watchlist_tickers
        )
        phases_completed = 1
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
                preset=preset,
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
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
            )

        # Phase 3: Liquidity Pre-filter + Options + Contracts
        options_result = await self._phase_options(scoring_result, universe_result, progress)
        phases_completed = 3
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
                preset=preset,
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
                options_result=options_result,
            )

        # Phase 4: Persist
        return await self._phase_persist(
            started_at=started_at,
            preset=preset,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=progress,
        )

    async def _phase_universe(
        self,
        preset: ScanPreset,
        progress: ProgressCallback,
        watchlist_tickers: list[str] | None = None,
    ) -> UniverseResult:
        """Phase 1: Fetch universe tickers, S&P 500 sectors, and OHLCV data.

        Steps:
            1. Fetch optionable tickers from CBOE (skipped in watchlist mode).
            2. Fetch S&P 500 constituents and build sector dict (skipped in watchlist mode).
            3. If preset is SP500, filter tickers to S&P 500 only (skipped in watchlist mode).
            4. Batch-fetch OHLCV for all tickers.
            5. Filter by minimum bar count (``ohlcv_min_bars``).
            6. Report progress.

        Returns:
            ``UniverseResult`` with tickers, OHLCV map, sectors, and counts.
        """
        tickers: list[str]
        sp500_sectors: dict[str, str]

        if watchlist_tickers is not None:
            # Watchlist mode: use provided tickers directly, skip Steps 1-3
            tickers = watchlist_tickers
            sp500_sectors = {}
            logger.info("Watchlist mode: %d tickers provided", len(tickers))
        else:
            # Step 1: Fetch optionable tickers
            all_tickers = await self._universe.fetch_optionable_tickers()
            logger.info("Universe: %d optionable tickers fetched", len(all_tickers))

            # Step 2: Fetch S&P 500 constituents
            sp500_constituents = await self._universe.fetch_sp500_constituents()
            sp500_sectors = {c.ticker: c.sector for c in sp500_constituents}
            logger.info("S&P 500: %d constituents fetched", len(sp500_sectors))

            # Step 3: Filter by preset
            if preset == ScanPreset.SP500:
                sp500_set = set(sp500_sectors.keys())
                tickers = [t for t in all_tickers if t in sp500_set]
                logger.info(
                    "SP500 preset: filtered %d -> %d tickers",
                    len(all_tickers),
                    len(tickers),
                )
            else:
                if preset == ScanPreset.ETFS:
                    logger.warning(
                        "ETFS preset selected but ETF-only filtering is not yet implemented; "
                        "using full universe (%d tickers)",
                        len(all_tickers),
                    )
                tickers = all_tickers

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
        scan_config = self._settings.scan
        for ts in scored:
            raw = raw_signals[ts.ticker]
            ts.direction = determine_direction(
                adx=raw.adx or 0.0,
                rsi=raw.rsi or 50.0,
                sma_alignment=raw.sma_alignment or 0.0,
                config=scan_config,
            )

        logger.info(
            "Scoring phase complete: %d tickers scored and classified",
            len(scored),
        )

        # Step 4: Report progress
        progress(ScanPhase.SCORING, len(universe_result.ohlcv_map), len(universe_result.ohlcv_map))

        return ScoringResult(
            scores=scored,
            raw_signals=raw_signals,
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

        liquid_scores: list[TickerScore] = []
        for ts in scoring_result.scores:
            ohlcv_list = ohlcv_map.get(ts.ticker)
            if ohlcv_list is None or len(ohlcv_list) == 0:
                continue

            avg_dollar_volume = sum(float(o.close) * o.volume for o in ohlcv_list) / len(
                ohlcv_list
            )
            latest_close = float(ohlcv_list[-1].close)

            if avg_dollar_volume >= min_dollar_volume and latest_close >= min_price:
                liquid_scores.append(ts)

        logger.info(
            "Liquidity pre-filter: %d -> %d tickers (min_dv=$%.0f, min_price=$%.0f)",
            len(scoring_result.scores),
            len(liquid_scores),
            min_dollar_volume,
            min_price,
        )

        # Step 2: Top-N selection (scores already sorted descending)
        top_n = self._settings.scan.top_n
        top_scores = liquid_scores[:top_n]

        logger.info("Top-N selection: %d tickers (top_n=%d)", len(top_scores), top_n)

        # Step 3: Fetch risk-free rate (once for entire scan, never raises)
        risk_free_rate: float = await self._fred.fetch_risk_free_rate()
        logger.info("Risk-free rate: %.4f", risk_free_rate)

        # Step 4: Per-ticker options processing in batches
        # Processing all tickers concurrently overwhelms the rate limiter,
        # causing timeouts. Batching ensures each batch's operations complete
        # well within the per-ticker timeout.
        progress(ScanPhase.OPTIONS, 0, len(top_scores))

        per_ticker_timeout = self._settings.scan.options_per_ticker_timeout
        batch_size = self._settings.scan.options_batch_size
        recommendations: dict[str, list[OptionContract]] = {}
        completed = 0

        for batch_start in range(0, len(top_scores), batch_size):
            batch = top_scores[batch_start : batch_start + batch_size]
            batch_tasks = [
                asyncio.wait_for(
                    self._process_ticker_options(ts, risk_free_rate),
                    timeout=per_ticker_timeout,
                )
                for ts in batch
            ]
            batch_results: list[
                tuple[str, list[OptionContract]] | BaseException
            ] = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for ts, result in zip(batch, batch_results, strict=True):
                if isinstance(result, BaseException):
                    logger.warning(
                        "Options processing failed for %s: %s: %s",
                        ts.ticker,
                        type(result).__name__,
                        result,
                    )
                else:
                    ticker, contracts = result
                    if contracts:
                        recommendations[ticker] = contracts
                completed += 1

            progress(ScanPhase.OPTIONS, completed, len(top_scores))

        logger.info(
            "Options phase complete: %d recommendations from %d tickers",
            len(recommendations),
            len(top_scores),
        )

        progress(ScanPhase.OPTIONS, len(top_scores), len(top_scores))

        return OptionsResult(
            recommendations=recommendations,
            risk_free_rate=risk_free_rate,
        )

    async def _process_ticker_options(
        self,
        ticker_score: TickerScore,
        risk_free_rate: float,
    ) -> tuple[str, list[OptionContract]]:
        """Fetch chains + ticker info for a single ticker and recommend contracts.

        Isolated per-ticker: exceptions propagate up to ``asyncio.gather``
        with ``return_exceptions=True``.

        Args:
            ticker_score: Scored ticker with direction set.
            risk_free_rate: Shared risk-free rate for this scan.

        Returns:
            Tuple of (ticker, recommended contracts).
        """
        ticker = ticker_score.ticker

        # Fetch chains and ticker info concurrently
        chain_task = self._options_data.fetch_chain_all_expirations(ticker)
        info_task = self._market_data.fetch_ticker_info(ticker)

        chain_results, ticker_info = await asyncio.gather(chain_task, info_task)

        # Flatten all contracts across expirations
        all_contracts: list[OptionContract] = []
        for chain in chain_results:
            all_contracts.extend(chain.contracts)

        if not all_contracts:
            logger.info("No contracts found for %s", ticker)
            return (ticker, [])

        spot = float(ticker_info.current_price)

        # Compute options-specific indicators from full chain before filtering
        options_signals = compute_options_indicators(all_contracts, spot)
        if options_signals.put_call_ratio is not None:
            ticker_score.signals.put_call_ratio = options_signals.put_call_ratio
        if options_signals.max_pain_distance is not None:
            ticker_score.signals.max_pain_distance = options_signals.max_pain_distance

        recommended = recommend_contracts(
            contracts=all_contracts,
            direction=ticker_score.direction,
            spot=spot,
            risk_free_rate=risk_free_rate,
            dividend_yield=ticker_info.dividend_yield,
            config=self._settings.pricing,
        )

        return (ticker, recommended)

    async def _phase_persist(
        self,
        *,
        started_at: datetime,
        preset: ScanPreset,
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
            tickers_scanned=len(universe_result.tickers),
            tickers_scored=len(scoring_result.scores),
            recommendations=recommendation_count,
        )

        # Step 2: Save scan run → get DB-assigned ID
        scan_id: int = await self._repository.save_scan_run(scan_run)
        logger.info("Persisted scan run id=%d", scan_id)

        # Step 3: Update scan_run_id on each TickerScore
        for ts in scoring_result.scores:
            ts.scan_run_id = scan_id

        # Step 4: Batch-insert ticker scores
        await self._repository.save_ticker_scores(scan_id, scoring_result.scores)
        logger.info(
            "Persisted %d ticker scores for scan %d",
            len(scoring_result.scores),
            scan_id,
        )

        # Step 5: Report progress
        progress(ScanPhase.PERSIST, 1, 1)

        # Step 6: Return final ScanResult
        # ScanRun is frozen — reconstruct with ID populated
        final_scan_run = ScanRun(
            id=scan_id,
            started_at=scan_run.started_at,
            completed_at=scan_run.completed_at,
            preset=scan_run.preset,
            tickers_scanned=scan_run.tickers_scanned,
            tickers_scored=scan_run.tickers_scored,
            recommendations=scan_run.recommendations,
        )

        return ScanResult(
            scan_run=final_scan_run,
            scores=scoring_result.scores,
            recommendations=options_result.recommendations,
            risk_free_rate=options_result.risk_free_rate,
            phases_completed=4,
        )

    def _make_cancelled_result(
        self,
        *,
        started_at: datetime,
        preset: ScanPreset,
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
                tickers_scanned=len(universe_result.tickers),
                tickers_scored=tickers_scored,
                recommendations=recommendation_count,
            ),
            scores=scores,
            recommendations=recommendations,
            risk_free_rate=risk_free_rate,
            cancelled=True,
            phases_completed=phases_completed,
        )
