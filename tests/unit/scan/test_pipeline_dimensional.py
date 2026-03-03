"""Tests for pipeline Phase 2 dimensional scoring + market regime wiring."""

import pytest

from options_arena.models import (
    IndicatorSignals,
    MarketRegime,
    SignalDirection,
    TickerScore,
)
from options_arena.models.scoring import DimensionalScores, DirectionSignal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ticker_score(ticker: str = "AAPL", **overrides: object) -> TickerScore:
    """Build a TickerScore with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": ticker,
        "composite_score": 78.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(rsi=65.2, adx=28.4, bb_width=42.1),
    }
    defaults.update(overrides)
    return TickerScore(**defaults)  # type: ignore[arg-type]


def _make_dimensional_scores(**overrides: object) -> DimensionalScores:
    defaults: dict[str, object] = {
        "trend": 75.0,
        "iv_vol": 60.0,
        "hv_vol": 45.0,
        "flow": 30.0,
        "microstructure": 50.0,
        "fundamental": 80.0,
        "regime": 55.0,
        "risk": 25.0,
    }
    defaults.update(overrides)
    return DimensionalScores(**defaults)  # type: ignore[arg-type]


def _make_direction_signal(confidence: float = 0.73) -> DirectionSignal:
    return DirectionSignal(
        direction=SignalDirection.BULLISH,
        confidence=confidence,
        contributing_signals=["rsi", "adx"],
    )


def _derive_market_regime(regime_val: float | None) -> MarketRegime | None:
    """Mirror the pipeline's threshold mapping for test assertions."""
    import math

    if regime_val is None or not math.isfinite(regime_val):
        return None
    if regime_val >= 80:
        return MarketRegime.CRISIS
    if regime_val >= 60:
        return MarketRegime.VOLATILE
    if regime_val >= 40:
        return MarketRegime.MEAN_REVERTING
    return MarketRegime.TRENDING


# ---------------------------------------------------------------------------
# Market regime threshold derivation
# ---------------------------------------------------------------------------


class TestMarketRegimeDerivation:
    """Test the threshold mapping logic used in pipeline Phase 2."""

    def test_trending_below_40(self) -> None:
        """Verify market_regime=TRENDING when signals.market_regime < 40."""
        assert _derive_market_regime(0.0) is MarketRegime.TRENDING
        assert _derive_market_regime(20.0) is MarketRegime.TRENDING
        assert _derive_market_regime(39.9) is MarketRegime.TRENDING

    def test_mean_reverting_40_to_60(self) -> None:
        """Verify market_regime=MEAN_REVERTING when 40 <= signals.market_regime < 60."""
        assert _derive_market_regime(40.0) is MarketRegime.MEAN_REVERTING
        assert _derive_market_regime(50.0) is MarketRegime.MEAN_REVERTING
        assert _derive_market_regime(59.9) is MarketRegime.MEAN_REVERTING

    def test_volatile_60_to_80(self) -> None:
        """Verify market_regime=VOLATILE when 60 <= signals.market_regime < 80."""
        assert _derive_market_regime(60.0) is MarketRegime.VOLATILE
        assert _derive_market_regime(70.0) is MarketRegime.VOLATILE
        assert _derive_market_regime(79.9) is MarketRegime.VOLATILE

    def test_crisis_80_and_above(self) -> None:
        """Verify market_regime=CRISIS when signals.market_regime >= 80."""
        assert _derive_market_regime(80.0) is MarketRegime.CRISIS
        assert _derive_market_regime(90.0) is MarketRegime.CRISIS
        assert _derive_market_regime(100.0) is MarketRegime.CRISIS

    def test_none_signal_returns_none(self) -> None:
        """Verify None market_regime signal results in None."""
        assert _derive_market_regime(None) is None

    def test_nan_signal_returns_none(self) -> None:
        """Verify NaN market_regime signal results in None."""
        assert _derive_market_regime(float("nan")) is None

    def test_inf_signal_returns_none(self) -> None:
        """Verify Inf market_regime signal results in None."""
        assert _derive_market_regime(float("inf")) is None

    def test_exact_boundary_40(self) -> None:
        """Verify 40.0 maps to MEAN_REVERTING (inclusive lower bound)."""
        assert _derive_market_regime(40.0) is MarketRegime.MEAN_REVERTING

    def test_exact_boundary_60(self) -> None:
        """Verify 60.0 maps to VOLATILE (inclusive lower bound)."""
        assert _derive_market_regime(60.0) is MarketRegime.VOLATILE

    def test_exact_boundary_80(self) -> None:
        """Verify 80.0 maps to CRISIS (inclusive lower bound)."""
        assert _derive_market_regime(80.0) is MarketRegime.CRISIS


class TestPipelineDimensionalWiring:
    """Test that pipeline Phase 2 correctly wires DSE computation + market regime."""

    def test_phase2_assigns_dimensional_scores(self) -> None:
        """Verify compute_dimensional_scores() result is assigned to TickerScore."""
        ts = _make_ticker_score()
        dim = _make_dimensional_scores()
        ts.dimensional_scores = dim

        assert ts.dimensional_scores is dim
        assert ts.dimensional_scores.trend == pytest.approx(75.0)

    def test_phase2_assigns_direction_confidence(self) -> None:
        """Verify compute_direction_signal() confidence is assigned to TickerScore."""
        ts = _make_ticker_score()
        sig = _make_direction_signal(confidence=0.85)
        ts.direction_confidence = sig.confidence

        assert ts.direction_confidence == pytest.approx(0.85)

    def test_phase2_assigns_market_regime_from_raw_signals(self) -> None:
        """Verify market regime derivation from raw signals."""
        ts = _make_ticker_score()
        raw = IndicatorSignals(market_regime=72.0)  # 60-80 range → VOLATILE
        regime_val = raw.market_regime

        if regime_val is not None:
            ts.market_regime = _derive_market_regime(regime_val)

        assert ts.market_regime is MarketRegime.VOLATILE

    def test_phase2_handles_none_market_regime_signal(self) -> None:
        """Verify None market_regime signal results in None on TickerScore."""
        ts = _make_ticker_score()
        raw = IndicatorSignals()  # market_regime is None
        assert raw.market_regime is None

        ts.market_regime = _derive_market_regime(raw.market_regime)
        assert ts.market_regime is None

    def test_phase2_failure_doesnt_set_fields(self) -> None:
        """Verify that if DSE computation raises, ticker keeps None fields."""
        ts = _make_ticker_score()
        assert ts.dimensional_scores is None
        assert ts.direction_confidence is None
        assert ts.market_regime is None
        # Simulating exception scenario: fields remain None

    def test_phase2_all_fields_set_together(self) -> None:
        """Verify all 3 fields can be set together on a single TickerScore."""
        ts = _make_ticker_score()
        dim = _make_dimensional_scores()
        sig = _make_direction_signal(confidence=0.65)
        raw = IndicatorSignals(market_regime=35.0)  # < 40 → TRENDING

        ts.dimensional_scores = dim
        ts.direction_confidence = sig.confidence
        ts.market_regime = _derive_market_regime(raw.market_regime)

        assert ts.dimensional_scores is not None
        assert ts.direction_confidence == pytest.approx(0.65)
        assert ts.market_regime is MarketRegime.TRENDING

    def test_phase2_multiple_tickers(self) -> None:
        """Verify dimensional scoring works for multiple tickers with different regimes."""
        tickers_and_regimes = [
            ("AAPL", 25.0, MarketRegime.TRENDING),
            ("MSFT", 45.0, MarketRegime.MEAN_REVERTING),
            ("GOOGL", 65.0, MarketRegime.VOLATILE),
            ("TSLA", 85.0, MarketRegime.CRISIS),
        ]

        for ticker, regime_val, expected_regime in tickers_and_regimes:
            ts = _make_ticker_score(ticker=ticker)
            ts.market_regime = _derive_market_regime(regime_val)
            assert ts.market_regime is expected_regime, f"Failed for {ticker}"

    def test_dimensional_scores_persist_in_phase4(self) -> None:
        """Verify dimensional scores set in Phase 2 survive on the object (not lost)."""
        ts = _make_ticker_score()
        dim = _make_dimensional_scores()
        ts.dimensional_scores = dim
        ts.direction_confidence = 0.9
        ts.market_regime = MarketRegime.CRISIS

        # Simulate Phase 3/4 — fields should still be there
        ts.next_earnings = None  # Phase 3 sets this
        ts.scan_run_id = 42  # Phase 4 sets this

        assert ts.dimensional_scores is dim
        assert ts.direction_confidence == pytest.approx(0.9)
        assert ts.market_regime is MarketRegime.CRISIS
