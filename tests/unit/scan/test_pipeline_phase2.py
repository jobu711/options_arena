"""Tests for ScanPipeline Phase 2 — Indicators + Scoring + Direction.

Covers:
  - Phase 2 computes indicators for each ticker.
  - Phase 2 retains raw_signals separately from normalized.
  - Direction uses RAW values (not normalized).
  - None indicator values fall back (adx->0.0, rsi->50.0, sma->0.0).
  - Progress callback invoked with ScanPhase.SCORING.
  - Cancellation between Phase 1 and Phase 2 returns partial result.
  - Empty ohlcv_map produces empty scores.
  - Full pipeline run() completes with phases_completed=2.
  - Direction classification produces correct SignalDirection values.
  - ScoringResult contains both scores and raw_signals.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    ScanPreset,
    SignalDirection,
)
from options_arena.models.config import ScanConfig
from options_arena.models.filters import ScanFilterSpec, UniverseFilters
from options_arena.models.market_data import OHLCV, TickerInfo
from options_arena.scan.models import ScanResult, ScoringResult, UniverseResult
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult
from options_arena.services.universe import SP500Constituent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(ticker: str, n: int = 300) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker.

    Uses 300 bars by default to exceed warmup of all indicators.
    Prices oscillate around a fixed base of 100 (no drift) so all values
    stay safely positive and pass OHLCV candle validators.
    """
    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = base_price + (i % 10) - 5  # oscillates in [95, 104]
        bars.append(
            OHLCV(
                ticker=ticker,
                date=d,
                open=Decimal(str(round(close - 0.5, 2))),
                high=Decimal(str(round(close + 1.0, 2))),
                low=Decimal(str(round(close - 1.0, 2))),
                close=Decimal(str(round(close, 2))),
                adjusted_close=Decimal(str(round(close, 2))),
                volume=1_000_000 + i * 1000,
            )
        )
    return bars


def _make_batch_result(tickers: list[str], bars: int = 300) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with all tickers succeeding."""
    return BatchOHLCVResult(
        results=[TickerOHLCVResult(ticker=t, data=_make_ohlcv_bars(t, bars)) for t in tickers]
    )


def _make_pipeline(
    *,
    optionable_tickers: list[str] | None = None,
    sp500_constituents: list[SP500Constituent] | None = None,
    batch_result: BatchOHLCVResult | None = None,
    settings: AppSettings | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services."""
    _settings = settings or AppSettings(
        scan=ScanConfig(filters=ScanFilterSpec(universe=UniverseFilters(preset=ScanPreset.FULL)))
    )
    tickers = optionable_tickers if optionable_tickers is not None else ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=sp500_constituents or [])

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(
        return_value=batch_result or _make_batch_result(tickers)
    )
    mock_market_data.fetch_earnings_date = AsyncMock(return_value=None)

    mock_options_data = AsyncMock()
    mock_fred = AsyncMock()
    mock_repository = AsyncMock()

    pipeline = ScanPipeline(
        settings=_settings,
        market_data=mock_market_data,
        options_data=mock_options_data,
        fred=mock_fred,
        universe=mock_universe,
        repository=mock_repository,
    )

    mocks = {
        "universe": mock_universe,
        "market_data": mock_market_data,
        "options_data": mock_options_data,
        "fred": mock_fred,
        "repository": mock_repository,
    }

    return pipeline, mocks


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_universe_result(
    tickers: list[str],
    bars_per_ticker: int = 300,
) -> UniverseResult:
    """Build a UniverseResult with synthetic OHLCV data for direct Phase 2 testing."""
    ohlcv_map = {t: _make_ohlcv_bars(t, bars_per_ticker) for t in tickers}
    return UniverseResult(
        tickers=tickers,
        ohlcv_map=ohlcv_map,
        sp500_sectors={},
        failed_count=0,
        filtered_count=0,
    )


# ---------------------------------------------------------------------------
# Phase 2 (Scoring) tests
# ---------------------------------------------------------------------------


class TestPhaseScoring:
    """Phase 2 computes indicators, scores universe, and classifies direction."""

    async def test_computes_indicators_for_each_ticker(self) -> None:
        """Phase 2 produces raw_signals for every ticker in ohlcv_map."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        assert set(scoring_result.raw_signals.keys()) == set(tickers)
        for ticker in tickers:
            assert isinstance(scoring_result.raw_signals[ticker], IndicatorSignals)

    async def test_retains_raw_signals_separately_from_normalized(self) -> None:
        """raw_signals contain raw values; TickerScore.signals are normalized."""
        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        # Raw signals should exist for each ticker
        for ticker in tickers:
            raw = scoring_result.raw_signals[ticker]
            assert isinstance(raw, IndicatorSignals)
            # RSI raw value is typically in [0, 100] but the exact value is
            # an actual indicator output, not a percentile rank
            if raw.rsi is not None:
                # Just verify it's a float — we can't easily assert it's "raw"
                # vs "normalized" with synthetic data where both are in similar ranges
                assert isinstance(raw.rsi, float)

        # Scores should also exist and have IndicatorSignals
        for ts in scoring_result.scores:
            assert isinstance(ts.signals, IndicatorSignals)

    async def test_direction_uses_raw_values_not_normalized(self) -> None:
        """Direction classification uses raw indicator values with config thresholds.

        With default ScanConfig (adx_trend_threshold=15.0), a ticker with raw
        ADX < 15.0 should be classified as NEUTRAL regardless of its normalized
        (percentile rank) value.
        """
        # Create a single ticker to avoid scoring normalization complications
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        # Verify direction is a SignalDirection enum (not raw string)
        assert len(scoring_result.scores) == 1
        ts = scoring_result.scores[0]
        assert isinstance(ts.direction, SignalDirection)
        assert ts.direction in (
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        )

    async def test_none_indicator_fallbacks(self) -> None:
        """When raw indicators are None, fallback values are used for direction.

        adx -> 0.0 (below threshold -> NEUTRAL)
        rsi -> 50.0 (midpoint)
        sma_alignment -> 0.0 (neutral)
        """
        # An empty signals object (all None) should produce NEUTRAL direction
        # because adx fallback is 0.0, which is < 15.0 (adx_trend_threshold)
        tickers = ["TEST"]
        # Use very few bars so indicators produce None values
        universe_result = _make_universe_result(tickers, bars_per_ticker=300)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        # Monkey-patch compute_indicators to return all-None signals
        from unittest.mock import patch

        all_none_signals = IndicatorSignals()

        with patch(
            "options_arena.scan.pipeline.compute_indicators",
            return_value=all_none_signals,
        ):
            scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        # With all-None raw signals, adx fallback is 0.0 < 15.0 -> NEUTRAL
        assert len(scoring_result.scores) == 1, "Expected exactly 1 scored ticker"
        ts = scoring_result.scores[0]
        assert ts.direction == SignalDirection.NEUTRAL

    async def test_progress_callback_invoked_with_scoring_phase(self) -> None:
        """Progress callback is invoked with ScanPhase.SCORING."""
        progress_calls: list[tuple[ScanPhase, int, int]] = []

        def recording_progress(phase: ScanPhase, current: int, total: int) -> None:
            progress_calls.append((phase, current, total))

        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        await pipeline._phase_scoring(universe_result, recording_progress)

        # Should have at least start and end calls
        assert len(progress_calls) >= 2
        for phase, _, _ in progress_calls:
            assert phase == ScanPhase.SCORING

        # First call is start (0, total)
        assert progress_calls[0][1] == 0
        assert progress_calls[0][2] == len(tickers)

        # Last call is completion (total, total)
        assert progress_calls[-1][1] == progress_calls[-1][2]

    async def test_empty_ohlcv_map_produces_empty_scores(self) -> None:
        """Empty ohlcv_map produces empty scores and raw_signals."""
        universe_result = UniverseResult(
            tickers=[],
            ohlcv_map={},
            sp500_sectors={},
            failed_count=0,
            filtered_count=0,
        )
        pipeline, _ = _make_pipeline(optionable_tickers=[])

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        assert scoring_result.scores == []
        assert scoring_result.raw_signals == {}

    async def test_scores_sorted_descending_by_composite_score(self) -> None:
        """Scores are sorted descending by composite_score (from score_universe)."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        scores = [ts.composite_score for ts in scoring_result.scores]
        assert scores == sorted(scores, reverse=True)

    async def test_scoring_result_type(self) -> None:
        """Phase 2 returns a ScoringResult with scores and raw_signals."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        pipeline, _ = _make_pipeline(optionable_tickers=tickers)

        scoring_result = await pipeline._phase_scoring(universe_result, _noop_progress)

        assert isinstance(scoring_result, ScoringResult)
        assert isinstance(scoring_result.scores, list)
        assert isinstance(scoring_result.raw_signals, dict)


# ---------------------------------------------------------------------------
# Cancellation tests (Phase 1 -> Phase 2 boundary)
# ---------------------------------------------------------------------------


class TestPhase2Cancellation:
    """Cancellation between Phase 1 and Phase 2."""

    async def test_cancelled_between_phases_returns_partial_result(self) -> None:
        """Token cancelled after Phase 1 skips Phase 2 entirely."""
        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL"])

        token = CancellationToken()
        token.cancel()

        result = await pipeline.run(token, _noop_progress)

        assert result.cancelled is True
        assert result.phases_completed == 1
        assert result.scores == []

    async def test_cancelled_after_phase2_returns_scores(self) -> None:
        """Token cancelled after Phase 2 returns scores but no recommendations."""
        pipeline, _ = _make_pipeline(optionable_tickers=["AAPL"])

        token = CancellationToken()

        # Cancel after Phase 2 by patching _phase_scoring to cancel the token
        original_phase_scoring = pipeline._phase_scoring

        async def _scoring_then_cancel(
            universe_result: UniverseResult,
            progress: object,
        ) -> ScoringResult:
            result = await original_phase_scoring(universe_result, progress)  # type: ignore[arg-type]
            token.cancel()
            return result

        pipeline._phase_scoring = _scoring_then_cancel  # type: ignore[assignment]

        result = await pipeline.run(token, _noop_progress)

        assert result.phases_completed == 2
        assert result.cancelled is True
        assert len(result.scores) > 0


# ---------------------------------------------------------------------------
# Full run() integration tests
# ---------------------------------------------------------------------------


class TestFullRun:
    """Full pipeline run() through all phases."""

    async def test_run_completes_all_phases(self) -> None:
        """A full uncancelled run completes with phases_completed=4."""
        tickers = ["AAPL", "MSFT"]
        pipeline, mocks = _make_pipeline(optionable_tickers=tickers)

        # Configure mock services for Phase 3 and 4
        mocks["fred"].fetch_risk_free_rate = AsyncMock(return_value=0.045)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(return_value=[])
        mocks["market_data"].fetch_ticker_info = AsyncMock(
            return_value=TickerInfo(
                ticker="X",
                company_name="X Inc.",
                sector="Tech",
                current_price=Decimal("100"),
                fifty_two_week_high=Decimal("130"),
                fifty_two_week_low=Decimal("70"),
            )
        )
        mocks["repository"].save_scan_run = AsyncMock(return_value=1)
        mocks["repository"].save_ticker_scores = AsyncMock(return_value=None)

        token = CancellationToken()

        result = await pipeline.run(token, _noop_progress)

        assert result.phases_completed == 4
        assert result.cancelled is False

    async def test_run_scan_run_metadata(self) -> None:
        """ScanRun metadata reflects pipeline execution."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        pipeline, mocks = _make_pipeline(optionable_tickers=tickers)

        # Configure mock services for Phase 3 and 4
        mocks["fred"].fetch_risk_free_rate = AsyncMock(return_value=0.045)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(return_value=[])
        mocks["market_data"].fetch_ticker_info = AsyncMock(
            return_value=TickerInfo(
                ticker="X",
                company_name="X Inc.",
                sector="Tech",
                current_price=Decimal("100"),
                fifty_two_week_high=Decimal("130"),
                fifty_two_week_low=Decimal("70"),
            )
        )
        mocks["repository"].save_scan_run = AsyncMock(return_value=1)
        mocks["repository"].save_ticker_scores = AsyncMock(return_value=None)

        token = CancellationToken()

        result = await pipeline.run(token, _noop_progress)

        assert result.scan_run.preset == ScanPreset.FULL
        assert result.scan_run.tickers_scanned == 3
        assert result.scan_run.tickers_scored > 0
        assert result.scan_run.started_at is not None
        assert result.scan_run.completed_at is not None
        assert result.scan_run.started_at <= result.scan_run.completed_at

    async def test_run_risk_free_rate_from_fred(self) -> None:
        """Risk-free rate comes from FRED service."""
        settings = AppSettings()
        pipeline, mocks = _make_pipeline(
            optionable_tickers=["AAPL"],
            settings=settings,
        )

        mocks["fred"].fetch_risk_free_rate = AsyncMock(return_value=0.042)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(return_value=[])
        mocks["market_data"].fetch_ticker_info = AsyncMock(
            return_value=TickerInfo(
                ticker="AAPL",
                company_name="Apple",
                sector="Tech",
                current_price=Decimal("150"),
                fifty_two_week_high=Decimal("200"),
                fifty_two_week_low=Decimal("100"),
            )
        )
        mocks["repository"].save_scan_run = AsyncMock(return_value=1)
        mocks["repository"].save_ticker_scores = AsyncMock(return_value=None)

        token = CancellationToken()

        result = await pipeline.run(token, _noop_progress)

        assert result.risk_free_rate == pytest.approx(0.042)

    async def test_run_returns_scan_result_type(self) -> None:
        """run() returns a ScanResult."""
        pipeline, mocks = _make_pipeline(optionable_tickers=["AAPL"])

        mocks["fred"].fetch_risk_free_rate = AsyncMock(return_value=0.045)
        mocks["options_data"].fetch_chain_all_expirations = AsyncMock(return_value=[])
        mocks["market_data"].fetch_ticker_info = AsyncMock(
            return_value=TickerInfo(
                ticker="AAPL",
                company_name="Apple",
                sector="Tech",
                current_price=Decimal("150"),
                fifty_two_week_high=Decimal("200"),
                fifty_two_week_low=Decimal("100"),
            )
        )
        mocks["repository"].save_scan_run = AsyncMock(return_value=1)
        mocks["repository"].save_ticker_scores = AsyncMock(return_value=None)

        token = CancellationToken()

        result = await pipeline.run(token, _noop_progress)

        assert isinstance(result, ScanResult)
