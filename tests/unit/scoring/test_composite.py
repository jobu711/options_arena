"""Unit tests for options_arena.scoring.composite."""

import math

import pytest

from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals, TickerScore
from options_arena.scoring.composite import (
    _FLOOR_VALUE,
    INDICATOR_WEIGHTS,
    composite_score,
    score_universe,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_INDICATOR_FIELDS: list[str] = list(IndicatorSignals.model_fields.keys())


def _make_uniform_signals(value: float) -> IndicatorSignals:
    """Build IndicatorSignals with all 18 fields set to *value*."""
    return IndicatorSignals(**{field: value for field in ALL_INDICATOR_FIELDS})


# ---------------------------------------------------------------------------
# composite_score
# ---------------------------------------------------------------------------


class TestCompositeScore:
    """Tests for composite_score()."""

    @pytest.mark.critical
    def test_known_values_geometric_mean(self) -> None:
        """Manually computed geometric mean for two indicators matches output.

        rsi=80 (weight 0.08), adx=40 (weight 0.08):
        exp((0.08*ln(80) + 0.08*ln(40)) / (0.08 + 0.08))
        = exp((0.08*4.38203 + 0.08*3.68888) / 0.16)
        = exp(0.64574 / 0.16)
        = exp(4.03589)
        = 56.59  (approx)
        """
        signals = IndicatorSignals(rsi=80.0, adx=40.0)
        result = composite_score(signals)

        expected = math.exp((0.08 * math.log(80.0) + 0.08 * math.log(40.0)) / (0.08 + 0.08))
        assert result == pytest.approx(expected, rel=1e-6)

    def test_weight_sum_approximately_one(self) -> None:
        """All INDICATOR_WEIGHTS values sum to ~1.0."""
        total = sum(weight for weight, _category in INDICATOR_WEIGHTS.values())
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_floor_substitution_zero_value(self) -> None:
        """Indicator value at 0.0 is treated as _FLOOR_VALUE (0.5) in log.

        rsi=0.0 -> floored to 0.5, ln(0.5) ≈ -0.693.
        Score = exp(0.07*ln(0.5) / 0.07) = exp(ln(0.5)) = 0.5.
        """
        signals = IndicatorSignals(rsi=0.0)
        result = composite_score(signals)
        # exp(0.07 * ln(0.5) / 0.07) = exp(ln(0.5)) = 0.5
        assert result == pytest.approx(0.5, rel=1e-6)

    def test_all_perfect_score(self) -> None:
        """All indicators at 100.0 produces composite = 100.0."""
        signals = _make_uniform_signals(100.0)
        result = composite_score(signals)
        assert result == pytest.approx(100.0, rel=1e-6)

    def test_all_minimum_score(self) -> None:
        """All indicators at _FLOOR_VALUE (0.5) produces composite ~= 0.5."""
        signals = _make_uniform_signals(_FLOOR_VALUE)
        result = composite_score(signals)
        assert result == pytest.approx(0.5, rel=1e-6)

    def test_missing_indicators_renormalized(self) -> None:
        """When some fields are None, only present fields contribute.

        rsi=80 (weight 0.08) alone:
        exp(0.08 * ln(80) / 0.08) = exp(ln(80)) = 80.0.
        """
        signals = IndicatorSignals(rsi=80.0)
        result = composite_score(signals)
        assert result == pytest.approx(80.0, rel=1e-6)

    def test_active_indicators_parameter(self) -> None:
        """Only indicators in the active_indicators set are used.

        Even though adx=40 is present on signals, it is excluded by
        active_indicators={rsi}. Result = exp(ln(80)) = 80.0.
        """
        signals = IndicatorSignals(rsi=80.0, adx=40.0)
        result = composite_score(signals, active_indicators={"rsi"})
        assert result == pytest.approx(80.0, rel=1e-6)

    def test_empty_signals_returns_zero(self) -> None:
        """All-None signals produce 0.0 (no weight accumulated)."""
        signals = IndicatorSignals()
        result = composite_score(signals)
        assert result == 0.0

    def test_clamping_upper_bound(self) -> None:
        """Result is clamped to 100.0 maximum.

        With geometric mean formula on percentile-ranked 0-100 data the
        theoretical max is 100.0 (all at 100), so this test confirms the
        clamp at boundary.
        """
        signals = _make_uniform_signals(100.0)
        result = composite_score(signals)
        assert result <= 100.0

    def test_clamping_lower_bound(self) -> None:
        """Result never goes below 0.0.

        With floor at 0.5, minimum possible = exp(ln(0.5)) = 0.5 > 0.0.
        But the clamp should still work logically.
        """
        signals = _make_uniform_signals(0.0)
        result = composite_score(signals)
        assert result >= 0.0

    def test_single_indicator_present(self) -> None:
        """With only one indicator, geometric mean equals that value.

        obv=50.0 (weight 0.05):
        exp(0.05 * ln(50) / 0.05) = exp(ln(50)) = 50.0.
        """
        signals = IndicatorSignals(obv=50.0)
        result = composite_score(signals)
        assert result == pytest.approx(50.0, rel=1e-6)

    def test_negative_value_floors_to_half(self) -> None:
        """A negative indicator value is floored to _FLOOR_VALUE = 0.5."""
        signals = IndicatorSignals(rsi=-5.0)
        result = composite_score(signals)
        # exp(0.07 * ln(0.5) / 0.07) = exp(ln(0.5)) = 0.5
        assert result == pytest.approx(0.5, rel=1e-6)

    def test_floor_value_is_half(self) -> None:
        """_FLOOR_VALUE is 0.5 so bottom-ranked tickers contribute negative signal."""
        assert pytest.approx(0.5) == _FLOOR_VALUE

    def test_all_weights_map_to_model_fields(self) -> None:
        """Every key in INDICATOR_WEIGHTS is a valid IndicatorSignals field."""
        model_fields = set(IndicatorSignals.model_fields.keys())
        for key in INDICATOR_WEIGHTS:
            assert key in model_fields, f"{key!r} is not an IndicatorSignals field"


# ---------------------------------------------------------------------------
# score_universe
# ---------------------------------------------------------------------------


class TestScoreUniverse:
    """Tests for score_universe()."""

    def test_end_to_end_three_tickers(self) -> None:
        """Three tickers with different raw signals produce a sorted list."""
        universe = {
            "HIGH": IndicatorSignals(rsi=80.0, adx=70.0, sma_alignment=90.0),
            "MID": IndicatorSignals(rsi=50.0, adx=50.0, sma_alignment=50.0),
            "LOW": IndicatorSignals(rsi=20.0, adx=30.0, sma_alignment=10.0),
        }
        results = score_universe(universe)

        assert len(results) == 3
        # Sorted descending by composite_score.
        assert results[0].composite_score >= results[1].composite_score
        assert results[1].composite_score >= results[2].composite_score
        # Top ticker should be HIGH (highest raw values -> highest percentile).
        assert results[0].ticker == "HIGH"
        assert results[-1].ticker == "LOW"

    def test_empty_universe(self) -> None:
        """Empty universe returns empty list."""
        assert score_universe({}) == []

    def test_all_same_values_similar_scores(self) -> None:
        """Tickers with identical raw values get similar composite scores.

        After percentile normalization with ties, all tickers get 50.0 for
        each indicator.  Composite = exp(ln(50)) = 50.0 for all.
        """
        signals = IndicatorSignals(rsi=50.0, adx=30.0)
        universe = {
            "A": signals,
            "B": signals,
            "C": signals,
        }
        results = score_universe(universe)

        scores = [r.composite_score for r in results]
        # All scores should be approximately equal.
        for score in scores:
            assert score == pytest.approx(scores[0], rel=1e-4)

    def test_missing_options_indicators_still_scores(self) -> None:
        """Tickers with None options indicators still produce valid scores.

        Only non-options indicators contribute; options indicators are
        excluded from the active set and weights renormalize.
        """
        universe = {
            "A": IndicatorSignals(rsi=80.0, adx=60.0, sma_alignment=70.0),
            "B": IndicatorSignals(rsi=40.0, adx=40.0, sma_alignment=30.0),
        }
        results = score_universe(universe)

        assert len(results) == 2
        for result in results:
            assert result.composite_score > 0.0
            # Options fields should be None on the signals.
            assert result.signals.iv_rank is None
            assert result.signals.iv_percentile is None

    def test_ticker_score_fields_populated(self) -> None:
        """TickerScore has correct field types and values."""
        universe = {
            "AAPL": IndicatorSignals(rsi=60.0, adx=50.0),
        }
        results = score_universe(universe)

        assert len(results) == 1
        ts = results[0]
        assert isinstance(ts, TickerScore)
        assert ts.ticker == "AAPL"
        assert isinstance(ts.composite_score, float)
        assert ts.composite_score > 0.0
        assert ts.direction == SignalDirection.NEUTRAL
        assert isinstance(ts.signals, IndicatorSignals)
        assert ts.scan_run_id is None
