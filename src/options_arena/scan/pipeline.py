"""Scan pipeline orchestration — 4-phase async pipeline.

Ties together ``services/``, ``indicators/``, ``scoring/``, and ``data/``
into a testable, cancellable, progress-reporting pipeline.  Replaces v3's
monolithic 430-line ``cli.py`` scan function with a ``ScanPipeline`` class.

Phase 1 (Universe) and Phase 2 (Scoring) are implemented in this module.
Phase 3 (Options) and Phase 4 (Persist) will be added in Issue #50.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from options_arena.data import Repository
from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    ScanPreset,
    ScanRun,
    TickerScore,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.indicators import (
    INDICATOR_REGISTRY,
    compute_indicators,
    ohlcv_to_dataframe,
)
from options_arena.scan.models import (
    ScanResult,
    ScoringResult,
    UniverseResult,
)
from options_arena.scan.progress import (
    CancellationToken,
    ProgressCallback,
    ScanPhase,
)
from options_arena.scoring import determine_direction, score_universe
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
    ) -> ScanResult:
        """Orchestrate all pipeline phases with cancellation checks between phases.

        Args:
            preset: Universe preset (FULL, SP500, ETFS).
            token: Instance-scoped cancellation token checked between phases.
            progress: Callback for reporting per-phase progress.

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

        # Phase 3 and Phase 4 will be added in Issue #50.
        # For now, return a result with phases_completed=2.
        return ScanResult(
            scan_run=ScanRun(
                started_at=started_at,
                completed_at=datetime.now(UTC),
                preset=preset,
                tickers_scanned=len(universe_result.tickers),
                tickers_scored=len(scoring_result.scores),
                recommendations=0,
            ),
            scores=scoring_result.scores,
            recommendations={},
            risk_free_rate=self._settings.pricing.risk_free_rate_fallback,
            phases_completed=2,
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

        # Step 2: Fetch S&P 500 constituents
        sp500_constituents = await self._universe.fetch_sp500_constituents()
        sp500_sectors: dict[str, str] = {c.ticker: c.sector for c in sp500_constituents}
        logger.info("S&P 500: %d constituents fetched", len(sp500_sectors))

        # Step 3: Filter by preset
        tickers: list[str]
        if preset == ScanPreset.SP500:
            sp500_set = set(sp500_sectors.keys())
            tickers = [t for t in all_tickers if t in sp500_set]
            logger.info(
                "SP500 preset: filtered %d -> %d tickers",
                len(all_tickers),
                len(tickers),
            )
        else:
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
        for ticker, ohlcv_list in universe_result.ohlcv_map.items():
            df = ohlcv_to_dataframe(ohlcv_list)
            raw_signals[ticker] = compute_indicators(df, INDICATOR_REGISTRY)

        logger.info("Computed indicators for %d tickers", len(raw_signals))

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

    def _make_cancelled_result(
        self,
        *,
        started_at: datetime,
        preset: ScanPreset,
        universe_result: UniverseResult,
        phases_completed: int,
        scoring_result: ScoringResult | None = None,
    ) -> ScanResult:
        """Build a partial ScanResult when the pipeline is cancelled.

        Args:
            started_at: Pipeline start time (UTC).
            preset: Scan preset used.
            universe_result: Phase 1 output.
            phases_completed: Number of phases completed before cancellation.
            scoring_result: Phase 2 output (None if cancelled after Phase 1).

        Returns:
            A ``ScanResult`` with ``cancelled=True`` and partial data.
        """
        scores = scoring_result.scores if scoring_result is not None else []
        tickers_scored = len(scores)

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
                recommendations=0,
            ),
            scores=scores,
            recommendations={},
            risk_free_rate=self._settings.pricing.risk_free_rate_fallback,
            cancelled=True,
            phases_completed=phases_completed,
        )
