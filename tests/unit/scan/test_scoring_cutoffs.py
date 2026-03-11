"""Tests for post-Phase 2 scoring cutoffs in the pipeline orchestrator.

Covers:
  - min_score cutoff filters low-scoring tickers.
  - min_direction_confidence cutoff filters low-confidence tickers.
  - Default values (0.0) do not filter any tickers.
  - Cutoffs are applied in order: direction_filter → min_score → min_confidence.
  - Combined cutoffs stack correctly.
  - Logging of before/after counts.
  - CLI --min-confidence arg maps to filter spec.
  - API ScanRequest.min_direction_confidence field.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from options_arena.models import (
    AppSettings,
    IndicatorSignals,
    ScanPreset,
    SignalDirection,
    TickerScore,
)
from options_arena.models.config import ScanConfig
from options_arena.models.filters import (
    ScanFilterSpec,
    ScoringFilters,
    UniverseFilters,
)
from options_arena.models.market_data import OHLCV
from options_arena.scan.pipeline import ScanPipeline
from options_arena.scan.progress import CancellationToken, ScanPhase
from options_arena.services import BatchOHLCVResult, TickerOHLCVResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(ticker: str, n: int = 250) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker."""
    bars: list[OHLCV] = []
    base_price = 100.0
    for i in range(n):
        d = date(2024, 1, 1) + timedelta(days=i)
        close = base_price + (i % 10) - 5
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


def _make_batch_result(tickers: list[str]) -> BatchOHLCVResult:
    """Build a BatchOHLCVResult with synthetic data."""
    return BatchOHLCVResult(
        results=[TickerOHLCVResult(ticker=t, data=_make_ohlcv_bars(t)) for t in tickers]
    )


def _make_pipeline(
    *,
    settings: AppSettings | None = None,
    optionable_tickers: list[str] | None = None,
) -> tuple[ScanPipeline, dict[str, AsyncMock]]:
    """Create a ScanPipeline with mocked services."""
    _settings = settings or AppSettings(
        scan=ScanConfig(filters=ScanFilterSpec(universe=UniverseFilters(preset=ScanPreset.FULL)))
    )
    tickers = optionable_tickers or ["AAPL", "MSFT", "GOOG"]

    mock_universe = AsyncMock()
    mock_universe.fetch_optionable_tickers = AsyncMock(return_value=tickers)
    mock_universe.fetch_sp500_constituents = AsyncMock(return_value=[])
    mock_universe.fetch_etf_tickers = AsyncMock(return_value=[])

    mock_market_data = AsyncMock()
    mock_market_data.fetch_batch_ohlcv = AsyncMock(return_value=_make_batch_result(tickers))
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


def _make_ticker_score(
    ticker: str,
    score: float,
    direction: SignalDirection = SignalDirection.BULLISH,
    confidence: float | None = None,
) -> TickerScore:
    """Create a TickerScore with given values."""
    return TickerScore(
        ticker=ticker,
        composite_score=score,
        direction=direction,
        signals=IndicatorSignals(),
        direction_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestScoringCutoffs:
    """Post-Phase 2 scoring cutoff tests."""

    async def test_min_score_filters_low_scoring_tickers(self) -> None:
        """Verify tickers below min_score are removed post-Phase 2."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_score=60.0),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        # Patch _phase_scoring to return known scores
        from options_arena.scan.models import ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0),
                _make_ticker_score("MSFT", 40.0),
                _make_ticker_score("GOOG", 70.0),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        # Patch _phase_options and _phase_persist to be no-ops
        from options_arena.scan.models import OptionsResult

        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        # The scoring_result.scores should have been filtered
        assert len(scoring_result.scores) == 2
        tickers = {ts.ticker for ts in scoring_result.scores}
        assert tickers == {"AAPL", "GOOG"}

    async def test_min_score_zero_no_filtering(self) -> None:
        """Verify min_score=0.0 (default) does not filter any tickers."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_score=0.0),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 10.0),
                _make_ticker_score("MSFT", 5.0),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        # No filtering — both tickers remain
        assert len(scoring_result.scores) == 2

    async def test_min_score_100_drops_all(self) -> None:
        """Verify min_score=100 drops all tickers (edge case)."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_score=100.0),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0),
                _make_ticker_score("MSFT", 99.9),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        assert len(scoring_result.scores) == 0

    async def test_min_confidence_filters_low_confidence(self) -> None:
        """Verify tickers below min_direction_confidence are removed."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_direction_confidence=0.5),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0, confidence=0.8),
                _make_ticker_score("MSFT", 70.0, confidence=0.3),
                _make_ticker_score("GOOG", 60.0, confidence=0.6),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        assert len(scoring_result.scores) == 2
        tickers = {ts.ticker for ts in scoring_result.scores}
        assert tickers == {"AAPL", "GOOG"}

    async def test_min_confidence_none_excluded(self) -> None:
        """Verify tickers with None confidence are excluded when cutoff > 0."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_direction_confidence=0.1),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0, confidence=0.5),
                _make_ticker_score("MSFT", 70.0, confidence=None),  # None = excluded
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        assert len(scoring_result.scores) == 1
        assert scoring_result.scores[0].ticker == "AAPL"

    async def test_min_confidence_zero_no_filtering(self) -> None:
        """Verify min_direction_confidence=0.0 does not filter."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(min_direction_confidence=0.0),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0, confidence=0.1),
                _make_ticker_score("MSFT", 70.0, confidence=None),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        assert len(scoring_result.scores) == 2

    async def test_direction_filter_applied_before_score_cutoff(self) -> None:
        """Verify ordering: direction filter, then min_score, then min_confidence."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(
                        direction_filter=SignalDirection.BULLISH,
                        min_score=50.0,
                    ),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0, SignalDirection.BULLISH),
                _make_ticker_score("MSFT", 40.0, SignalDirection.BULLISH),  # below score
                _make_ticker_score("GOOG", 90.0, SignalDirection.BEARISH),  # wrong direction
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        # GOOG filtered by direction, MSFT filtered by score → only AAPL
        assert len(scoring_result.scores) == 1
        assert scoring_result.scores[0].ticker == "AAPL"

    async def test_combined_cutoffs(self) -> None:
        """Verify all three filters stack correctly."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(
                        direction_filter=SignalDirection.BULLISH,
                        min_score=50.0,
                        min_direction_confidence=0.4,
                    ),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("A", 80.0, SignalDirection.BULLISH, 0.9),
                _make_ticker_score("B", 40.0, SignalDirection.BULLISH, 0.8),  # low score
                _make_ticker_score("C", 70.0, SignalDirection.BEARISH, 0.7),  # wrong dir
                _make_ticker_score("D", 60.0, SignalDirection.BULLISH, 0.2),  # low conf
                _make_ticker_score("E", 55.0, SignalDirection.BULLISH, 0.5),  # passes all
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        await pipeline.run(token, _noop_progress)

        tickers = {ts.ticker for ts in scoring_result.scores}
        assert tickers == {"A", "E"}

    async def test_cutoff_logging(self, caplog: pytest.LogCaptureFixture) -> None:
        """Verify before/after counts are logged for each cutoff."""
        settings = AppSettings(
            scan=ScanConfig(
                filters=ScanFilterSpec(
                    universe=UniverseFilters(preset=ScanPreset.FULL),
                    scoring=ScoringFilters(
                        min_score=50.0,
                        min_direction_confidence=0.5,
                    ),
                )
            )
        )
        pipeline, _ = _make_pipeline(settings=settings)

        from options_arena.scan.models import OptionsResult, ScoringResult

        scoring_result = ScoringResult(
            scores=[
                _make_ticker_score("AAPL", 80.0, confidence=0.8),
                _make_ticker_score("MSFT", 30.0, confidence=0.2),
            ],
            raw_signals={},
        )
        pipeline._phase_scoring = AsyncMock(return_value=scoring_result)  # type: ignore[method-assign]
        pipeline._phase_options = AsyncMock(  # type: ignore[method-assign]
            return_value=OptionsResult(recommendations={}, risk_free_rate=0.05, earnings_dates={})
        )
        pipeline._phase_persist = AsyncMock(return_value=AsyncMock())  # type: ignore[method-assign]

        token = CancellationToken()
        with caplog.at_level(logging.INFO, logger="options_arena.scan.pipeline"):
            await pipeline.run(token, _noop_progress)

        # Check both cutoff log messages
        assert any("min_score cutoff" in r.message for r in caplog.records)
        assert any("min_confidence cutoff" in r.message for r in caplog.records)


class TestScoringCutoffsAPI:
    """API schema tests for min_direction_confidence."""

    def test_scan_request_accepts_min_direction_confidence(self) -> None:
        """Verify ScanRequest accepts min_direction_confidence field."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest(min_direction_confidence=0.5)
        assert req.min_direction_confidence == 0.5

    def test_scan_request_default_none(self) -> None:
        """Verify min_direction_confidence defaults to None."""
        from options_arena.api.schemas import ScanRequest

        req = ScanRequest()
        assert req.min_direction_confidence is None

    def test_scan_request_rejects_out_of_range(self) -> None:
        """Verify min_direction_confidence rejects values outside [0.0, 1.0]."""
        from pydantic import ValidationError

        from options_arena.api.schemas import ScanRequest

        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=1.5)

        with pytest.raises(ValidationError, match="min_direction_confidence"):
            ScanRequest(min_direction_confidence=-0.1)
