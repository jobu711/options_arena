"""Scan pipeline orchestration — 4-phase async pipeline.

Thin orchestrator that delegates to standalone phase functions in
``phase_universe``, ``phase_scoring``, ``phase_options``, and
``phase_persist``.  Cross-phase concerns (cancellation, direction
filter, earnings propagation) remain here.

Imports of ``compute_indicators``, ``recommend_contracts``, and
``map_yfinance_to_metadata`` are retained so that tests patching
``options_arena.scan.pipeline.<name>`` continue to work — the wrapper
methods pass these module-level references into the phase functions.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd

from options_arena.data import Repository
from options_arena.models import (
    AppSettings,
    OptionContract,
    ScanRun,
    ScanSource,
    SpreadAnalysis,
    TickerScore,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.indicators import compute_indicators  # kept for test-patching
from options_arena.scan.models import (
    OptionsResult,
    ScanResult,
    ScoringResult,
    UniverseResult,
)
from options_arena.scan.phase_options import (
    process_ticker_options,
    run_options_phase,
)
from options_arena.scan.phase_persist import run_persist_phase
from options_arena.scan.phase_scoring import run_scoring_phase
from options_arena.scan.phase_universe import run_universe_phase
from options_arena.scan.progress import (
    CancellationToken,
    ProgressCallback,
)
from options_arena.scoring import recommend_contracts  # kept for test-patching
from options_arena.services import (
    FredService,
    MarketDataService,
    OptionsDataService,
    UniverseService,
)
from options_arena.services.universe import (
    map_yfinance_to_metadata,  # kept for test-patching
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

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        token: CancellationToken,
        progress: ProgressCallback,
        source: ScanSource = ScanSource.MANUAL,
    ) -> ScanResult:
        """Orchestrate all pipeline phases with cancellation checks between phases.

        Args:
            token: Instance-scoped cancellation token checked between phases.
            progress: Callback for reporting per-phase progress.
            source: Origin of the scan (manual).

        Returns:
            A ``ScanResult`` with all phases completed (or partial if cancelled).
        """
        started_at = datetime.now(UTC)
        phases_completed = 0

        # Phase 1: Universe + OHLCV
        universe_result = await self._phase_universe(progress)
        phases_completed = 1
        if token.is_cancelled:
            return self._make_cancelled_result(
                started_at=started_at,
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
                source=source,
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
            )

        # Post-Phase 2: Apply scoring filters (direction, min_score, min_confidence)
        scoring_filters = self._settings.scan.filters.scoring

        if scoring_filters.direction_filter is not None:
            before_count = len(scoring_result.scores)
            scoring_result.scores = [
                ts
                for ts in scoring_result.scores
                if ts.direction == scoring_filters.direction_filter
            ]
            logger.info(
                "Direction filter (%s): %d -> %d tickers",
                scoring_filters.direction_filter.value,
                before_count,
                len(scoring_result.scores),
            )

        if scoring_filters.min_score > 0.0:
            before_count = len(scoring_result.scores)
            scoring_result.scores = [
                ts
                for ts in scoring_result.scores
                if ts.composite_score >= scoring_filters.min_score
            ]
            logger.info(
                "min_score cutoff (%.1f): %d -> %d tickers",
                scoring_filters.min_score,
                before_count,
                len(scoring_result.scores),
            )

        if scoring_filters.min_direction_confidence > 0.0:
            before_count = len(scoring_result.scores)
            scoring_result.scores = [
                ts
                for ts in scoring_result.scores
                if ts.direction_confidence is not None
                and ts.direction_confidence >= scoring_filters.min_direction_confidence
            ]
            logger.info(
                "min_confidence cutoff (%.2f): %d -> %d tickers",
                scoring_filters.min_direction_confidence,
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
                source=source,
                universe_result=universe_result,
                phases_completed=phases_completed,
                scoring_result=scoring_result,
                options_result=options_result,
            )

        # Phase 4: Persist
        return await self._phase_persist(
            started_at=started_at,
            source=source,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=progress,
        )

    # ------------------------------------------------------------------
    # Phase wrappers — thin delegations to standalone phase functions
    # ------------------------------------------------------------------

    async def _phase_universe(
        self,
        progress: ProgressCallback,
    ) -> UniverseResult:
        """Phase 1: Fetch universe tickers, S&P 500 sectors, and OHLCV data."""
        return await run_universe_phase(
            progress,
            universe=self._universe,
            market_data=self._market_data,
            repository=self._repository,
            universe_filters=self._settings.scan.filters.universe,
        )

    async def _phase_scoring(
        self,
        universe_result: UniverseResult,
        progress: ProgressCallback,
    ) -> ScoringResult:
        """Phase 2: Compute indicators, score universe, classify direction."""
        return await run_scoring_phase(
            universe_result,
            progress,
            scan_config=self._settings.scan,
            compute_indicators_fn=compute_indicators,
        )

    async def _phase_options(
        self,
        scoring_result: ScoringResult,
        universe_result: UniverseResult,
        progress: ProgressCallback,
    ) -> OptionsResult:
        """Phase 3: Liquidity pre-filter, top-N selection, options + contracts."""
        return await run_options_phase(
            scoring_result,
            universe_result,
            progress,
            fred=self._fred,
            market_data=self._market_data,
            options_data=self._options_data,
            repository=self._repository,
            scan_config=self._settings.scan,
            options_filters=self._settings.scan.filters.options,
            universe_filters=self._settings.scan.filters.universe,
            pricing_config=self._settings.pricing,
            spread_config=self._settings.spread,
            process_ticker_fn=self._process_ticker_options,
        )

    async def _process_ticker_options(
        self,
        ticker_score: TickerScore,
        risk_free_rate: float,
        ohlcv_map: dict[str, list[OHLCV]],
        spx_close: pd.Series | None,
    ) -> tuple[str, list[OptionContract], date | None, Decimal | None, SpreadAnalysis | None]:
        """Fetch chains + ticker info + earnings date for a single ticker."""
        return await process_ticker_options(
            ticker_score,
            risk_free_rate,
            ohlcv_map,
            spx_close,
            market_data=self._market_data,
            options_data=self._options_data,
            repository=self._repository,
            options_filters=self._settings.scan.filters.options,
            universe_filters=self._settings.scan.filters.universe,
            pricing_config=self._settings.pricing,
            spread_config=self._settings.spread,
            recommend_contracts_fn=recommend_contracts,
            map_yfinance_fn=map_yfinance_to_metadata,
        )

    async def _phase_persist(
        self,
        *,
        started_at: datetime,
        source: ScanSource,
        universe_result: UniverseResult,
        scoring_result: ScoringResult,
        options_result: OptionsResult,
        progress: ProgressCallback,
    ) -> ScanResult:
        """Phase 4: Persist scan results to the database."""
        preset = self._settings.scan.filters.universe.preset
        return await run_persist_phase(
            started_at=started_at,
            preset=preset,
            source=source,
            universe_result=universe_result,
            scoring_result=scoring_result,
            options_result=options_result,
            progress=progress,
            repository=self._repository,
            filter_spec=self._settings.scan.filters,
        )

    # ------------------------------------------------------------------
    # Cancellation helper
    # ------------------------------------------------------------------

    def _make_cancelled_result(
        self,
        *,
        started_at: datetime,
        source: ScanSource,
        universe_result: UniverseResult,
        phases_completed: int,
        scoring_result: ScoringResult | None = None,
        options_result: OptionsResult | None = None,
    ) -> ScanResult:
        """Build a partial ScanResult when the pipeline is cancelled.

        Args:
            started_at: Pipeline start time (UTC).
            source: How the scan was triggered.
            universe_result: Phase 1 output.
            phases_completed: Number of phases completed before cancellation.
            scoring_result: Phase 2 output (None if cancelled after Phase 1).
            options_result: Phase 3 output (None if cancelled before Phase 3).

        Returns:
            A ``ScanResult`` with ``cancelled=True`` and partial data.
        """
        preset = self._settings.scan.filters.universe.preset
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
                filter_spec_json=self._settings.scan.filters.model_dump_json(),
            ),
            scores=scores,
            recommendations=recommendations,
            risk_free_rate=risk_free_rate,
            earnings_dates=earnings_dates,
            cancelled=True,
            phases_completed=phases_completed,
        )
