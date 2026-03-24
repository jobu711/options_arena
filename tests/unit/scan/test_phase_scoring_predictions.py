"""Tests for scan pipeline prediction recording in Phase 2.

Validates:
- One ``Prediction`` per ``TickerScore`` in ``ScoringResult``.
- Prediction direction matches ``TickerScore.direction``.
- Context fields (``adx``, ``rsi``, ``atr_pct``) populated from ``raw_signals``.
- ``iv_rank`` is ``None`` in Phase 2 (options data not yet fetched).
- ``scan_run_id`` is 0 (placeholder for orchestrator).
- ``ScoringResult`` defaults to empty ``scan_predictions`` list.
- Prediction creation failure for one ticker does not block others.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest

from options_arena.models import (
    ScanPreset,
    SignalDirection,
)
from options_arena.models.attribution import Prediction, PredictionSource
from options_arena.models.config import ScanConfig
from options_arena.models.filters import ScanFilterSpec, UniverseFilters
from options_arena.models.market_data import OHLCV
from options_arena.scan.models import ScoringResult, UniverseResult
from options_arena.scan.phase_scoring import run_scoring_phase
from options_arena.scan.progress import ScanPhase

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ohlcv_bars(ticker: str, n: int = 300) -> list[OHLCV]:
    """Generate *n* synthetic OHLCV bars for a ticker.

    Uses 300 bars by default to exceed warmup of all indicators.
    Prices oscillate around a fixed base of 100.
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
            ),
        )
    return bars


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


def _noop_progress(phase: ScanPhase, current: int, total: int) -> None:
    """No-op progress callback."""


def _make_scan_config() -> ScanConfig:
    """Create a default ScanConfig for testing."""
    return ScanConfig(
        filters=ScanFilterSpec(universe=UniverseFilters(preset=ScanPreset.FULL)),
    )


# ---------------------------------------------------------------------------
# Tests: Scan prediction recording
# ---------------------------------------------------------------------------


class TestScanPredictionRecording:
    """Prediction creation after direction + confidence assignment in Phase 2."""

    @pytest.mark.critical
    async def test_predictions_created_per_ticker(self) -> None:
        """One Prediction per TickerScore in ScoringResult."""
        tickers = ["AAPL", "MSFT", "GOOG"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == len(result.scores)
        prediction_tickers = {p.ticker for p in result.scan_predictions}
        score_tickers = {ts.ticker for ts in result.scores}
        assert prediction_tickers == score_tickers

    async def test_prediction_direction_matches_ticker_score(self) -> None:
        """Prediction.predicted_direction == TickerScore.direction."""
        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        score_directions = {ts.ticker: ts.direction for ts in result.scores}
        for pred in result.scan_predictions:
            assert pred.predicted_direction == score_directions[pred.ticker]

    async def test_prediction_source_is_scan_direction(self) -> None:
        """All predictions have source=SCAN_DIRECTION."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        assert result.scan_predictions[0].source == PredictionSource.SCAN_DIRECTION

    async def test_context_from_raw_signals(self) -> None:
        """Prediction context fields populated from raw_signals dict."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        pred = result.scan_predictions[0]
        raw = result.raw_signals["AAPL"]

        # adx and rsi should match raw signals (may be None if not computed)
        assert pred.adx == raw.adx
        assert pred.rsi == raw.rsi
        assert pred.atr_pct == raw.atr_pct

    async def test_iv_rank_none_when_missing(self) -> None:
        """iv_rank=None when not available in Phase 2 signals.

        Options data (iv_rank) is not fetched until Phase 3, so Phase 2
        raw signals will have iv_rank=None.
        """
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        pred = result.scan_predictions[0]
        # Phase 2 raw signals won't have iv_rank populated
        assert pred.iv_rank is None

    async def test_scan_run_id_placeholder(self) -> None:
        """scan_run_id=0 (placeholder for orchestrator to set)."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        for pred in result.scan_predictions:
            assert pred.scan_run_id == 0

    async def test_prediction_confidence_from_direction_confidence(self) -> None:
        """Prediction.confidence uses TickerScore.direction_confidence."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        pred = result.scan_predictions[0]
        ts = result.scores[0]

        if ts.direction_confidence is not None:
            assert pred.confidence == pytest.approx(ts.direction_confidence, abs=0.01)
        else:
            # Fallback to 0.5 when direction_confidence is None
            assert pred.confidence == pytest.approx(0.5, abs=0.01)

    async def test_prediction_created_at_is_utc(self) -> None:
        """Prediction.created_at is a UTC datetime."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        pred = result.scan_predictions[0]
        assert pred.created_at.tzinfo is not None
        assert pred.created_at.utcoffset() == timedelta(0)

    async def test_predictions_are_frozen(self) -> None:
        """Prediction model is frozen — fields are immutable after construction."""
        tickers = ["AAPL"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert len(result.scan_predictions) == 1
        pred = result.scan_predictions[0]
        with pytest.raises(Exception):  # noqa: B017
            pred.ticker = "MSFT"  # type: ignore[misc]


class TestScoringResultDefaults:
    """ScoringResult model defaults for scan_predictions field."""

    def test_scoring_result_default_empty(self) -> None:
        """ScoringResult() without predictions has empty list."""
        result = ScoringResult(
            scores=[],
            raw_signals={},
        )
        assert result.scan_predictions == []

    def test_scoring_result_with_predictions(self) -> None:
        """ScoringResult accepts a list of Predictions."""
        pred = Prediction(
            scan_run_id=0,
            ticker="AAPL",
            source=PredictionSource.SCAN_DIRECTION,
            predicted_direction=SignalDirection.BULLISH,
            confidence=0.7,
            created_at=datetime.now(UTC),
        )
        result = ScoringResult(
            scores=[],
            raw_signals={},
            scan_predictions=[pred],
        )
        assert len(result.scan_predictions) == 1
        assert result.scan_predictions[0].ticker == "AAPL"


class TestPredictionCreationFailure:
    """Prediction creation failure for one ticker does not block others."""

    async def test_prediction_creation_failure_skipped(self) -> None:
        """Bad ticker data causes prediction skip, others still created."""
        tickers = ["AAPL", "MSFT"]
        universe_result = _make_universe_result(tickers)
        config = _make_scan_config()

        # Patch Prediction constructor to fail for the first call only
        original_init = Prediction.__init__
        call_count = 0

        def failing_init(self: Prediction, **kwargs: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("simulated failure")
            original_init(self, **kwargs)

        with patch.object(Prediction, "__init__", failing_init):
            result = await run_scoring_phase(
                universe_result,
                _noop_progress,
                scan_config=config,
            )

        # At least one prediction should survive despite one failure
        assert len(result.scan_predictions) >= 1
        # Should have fewer predictions than scored tickers
        assert len(result.scan_predictions) < len(result.scores)

    async def test_empty_universe_produces_no_predictions(self) -> None:
        """Zero tickers scored yields empty scan_predictions list."""
        universe_result = _make_universe_result([])
        config = _make_scan_config()

        result = await run_scoring_phase(
            universe_result,
            _noop_progress,
            scan_config=config,
        )

        assert result.scan_predictions == []
        assert result.scores == []
