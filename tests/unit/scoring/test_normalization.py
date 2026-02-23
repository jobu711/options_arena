"""Unit tests for options_arena.scoring.normalization."""

import pytest

from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.normalization import (
    INVERTED_INDICATORS,
    get_active_indicators,
    invert_indicators,
    percentile_rank_normalize,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _field_val(signals: IndicatorSignals, field: str) -> float | None:
    """Extract a single field value from IndicatorSignals."""
    return getattr(signals, field)


ALL_FIELDS: list[str] = list(IndicatorSignals.model_fields.keys())


# ---------------------------------------------------------------------------
# percentile_rank_normalize
# ---------------------------------------------------------------------------


class TestPercentileRankNormalize:
    """Tests for percentile_rank_normalize()."""

    def test_basic_ranking_three_tickers(self) -> None:
        """Three tickers with distinct RSI values produce correct percentile ranks."""
        universe = {
            "LOW": IndicatorSignals(rsi=20.0),
            "MID": IndicatorSignals(rsi=50.0),
            "HIGH": IndicatorSignals(rsi=80.0),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["LOW"], "rsi") == pytest.approx(0.0)
        assert _field_val(result["MID"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["HIGH"], "rsi") == pytest.approx(100.0)

    def test_tie_handling_all_same(self) -> None:
        """Three tickers with identical RSI all receive 50.0 (tied average)."""
        universe = {
            "A": IndicatorSignals(rsi=50.0),
            "B": IndicatorSignals(rsi=50.0),
            "C": IndicatorSignals(rsi=50.0),
        }
        result = percentile_rank_normalize(universe)

        # All tied at avg_rank=2.0, percentile = (2-1)/(3-1)*100 = 50.0
        assert _field_val(result["A"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["B"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["C"], "rsi") == pytest.approx(50.0)

    def test_single_ticker_gets_midpoint(self) -> None:
        """A single ticker in the universe receives 50.0 for all indicators."""
        universe = {
            "ONLY": IndicatorSignals(
                rsi=60.0,
                adx=30.0,
                bb_width=0.05,
                sma_alignment=0.8,
            ),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["ONLY"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["ONLY"], "adx") == pytest.approx(50.0)
        assert _field_val(result["ONLY"], "bb_width") == pytest.approx(50.0)
        assert _field_val(result["ONLY"], "sma_alignment") == pytest.approx(50.0)

    def test_missing_indicator_excluded(self) -> None:
        """A ticker missing an indicator gets None; others are ranked among non-None."""
        universe = {
            "HAS": IndicatorSignals(rsi=60.0),
            "MISSING": IndicatorSignals(rsi=None),
            "ALSO_HAS": IndicatorSignals(rsi=40.0),
        }
        result = percentile_rank_normalize(universe)

        # Only HAS and ALSO_HAS participate: ALSO_HAS=0.0, HAS=100.0
        assert _field_val(result["HAS"], "rsi") == pytest.approx(100.0)
        assert _field_val(result["ALSO_HAS"], "rsi") == pytest.approx(0.0)
        assert _field_val(result["MISSING"], "rsi") is None

    def test_universally_missing_stays_none(self) -> None:
        """When all tickers have None for an indicator, output is also None."""
        universe = {
            "A": IndicatorSignals(iv_rank=None),
            "B": IndicatorSignals(iv_rank=None),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["A"], "iv_rank") is None
        assert _field_val(result["B"], "iv_rank") is None

    def test_empty_universe(self) -> None:
        """Empty universe returns empty dict."""
        result = percentile_rank_normalize({})
        assert result == {}

    def test_all_same_values_two_tickers(self) -> None:
        """Two tickers with same value: each gets 50.0 (tied average)."""
        universe = {
            "A": IndicatorSignals(rsi=50.0),
            "B": IndicatorSignals(rsi=50.0),
        }
        result = percentile_rank_normalize(universe)

        # avg_rank=1.5, percentile = (1.5-1)/(2-1)*100 = 50.0
        assert _field_val(result["A"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["B"], "rsi") == pytest.approx(50.0)

    def test_two_tickers_distinct(self) -> None:
        """Two tickers with distinct values get 0.0 and 100.0."""
        universe = {
            "LOW": IndicatorSignals(adx=10.0),
            "HIGH": IndicatorSignals(adx=30.0),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["LOW"], "adx") == pytest.approx(0.0)
        assert _field_val(result["HIGH"], "adx") == pytest.approx(100.0)

    def test_mixed_none_and_present(self) -> None:
        """Partial indicator coverage: rank only among tickers that have values."""
        universe = {
            "A": IndicatorSignals(rsi=70.0, adx=20.0),
            "B": IndicatorSignals(rsi=30.0, adx=None),
            "C": IndicatorSignals(rsi=None, adx=40.0),
        }
        result = percentile_rank_normalize(universe)

        # RSI: A=70, B=30 -> B=0.0, A=100.0; C=None
        assert _field_val(result["A"], "rsi") == pytest.approx(100.0)
        assert _field_val(result["B"], "rsi") == pytest.approx(0.0)
        assert _field_val(result["C"], "rsi") is None

        # ADX: A=20, C=40 -> A=0.0, C=100.0; B=None
        assert _field_val(result["A"], "adx") == pytest.approx(0.0)
        assert _field_val(result["C"], "adx") == pytest.approx(100.0)
        assert _field_val(result["B"], "adx") is None

    def test_nan_treated_as_missing(self) -> None:
        """NaN values are treated identically to None."""
        universe = {
            "VALID": IndicatorSignals(rsi=50.0),
            "NAN": IndicatorSignals(rsi=float("nan")),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["VALID"], "rsi") == pytest.approx(50.0)
        assert _field_val(result["NAN"], "rsi") is None

    def test_all_fields_populated(self) -> None:
        """When all 18 fields are populated, every field gets a rank."""
        full_signals = IndicatorSignals(
            rsi=50.0,
            stochastic_rsi=50.0,
            williams_r=50.0,
            adx=50.0,
            roc=50.0,
            supertrend=50.0,
            atr_pct=50.0,
            bb_width=50.0,
            keltner_width=50.0,
            obv=50.0,
            ad=50.0,
            relative_volume=50.0,
            sma_alignment=50.0,
            vwap_deviation=50.0,
            iv_rank=50.0,
            iv_percentile=50.0,
            put_call_ratio=50.0,
            max_pain_distance=50.0,
        )
        universe = {"ONLY": full_signals}
        result = percentile_rank_normalize(universe)

        for field in ALL_FIELDS:
            assert _field_val(result["ONLY"], field) == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# invert_indicators
# ---------------------------------------------------------------------------


class TestInvertIndicators:
    """Tests for invert_indicators()."""

    def test_inverted_indicator_flipped(self) -> None:
        """Inverted indicator bb_width: high value becomes low after inversion."""
        normalized = {
            "AAPL": IndicatorSignals(bb_width=80.0, rsi=60.0),
        }
        result = invert_indicators(normalized)

        assert _field_val(result["AAPL"], "bb_width") == pytest.approx(20.0)
        # Non-inverted indicator unchanged.
        assert _field_val(result["AAPL"], "rsi") == pytest.approx(60.0)

    def test_inversion_preserves_none(self) -> None:
        """None values for inverted indicators stay None."""
        normalized = {
            "TSLA": IndicatorSignals(atr_pct=None, keltner_width=None),
        }
        result = invert_indicators(normalized)

        assert _field_val(result["TSLA"], "atr_pct") is None
        assert _field_val(result["TSLA"], "keltner_width") is None

    def test_all_inverted_indicators_flipped(self) -> None:
        """Every indicator in INVERTED_INDICATORS is correctly flipped."""
        kwargs: dict[str, float | None] = {field: 75.0 for field in INVERTED_INDICATORS}
        normalized = {"X": IndicatorSignals(**kwargs)}
        result = invert_indicators(normalized)

        for field in INVERTED_INDICATORS:
            assert _field_val(result["X"], field) == pytest.approx(25.0)

    def test_non_inverted_unchanged(self) -> None:
        """Non-inverted indicators are untouched by inversion."""
        normalized = {
            "SPY": IndicatorSignals(rsi=40.0, adx=60.0, obv=80.0),
        }
        result = invert_indicators(normalized)

        assert _field_val(result["SPY"], "rsi") == pytest.approx(40.0)
        assert _field_val(result["SPY"], "adx") == pytest.approx(60.0)
        assert _field_val(result["SPY"], "obv") == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# get_active_indicators
# ---------------------------------------------------------------------------


class TestGetActiveIndicators:
    """Tests for get_active_indicators()."""

    def test_returns_non_none_fields(self) -> None:
        """Returns fields that have at least one non-None value."""
        universe = {
            "A": IndicatorSignals(rsi=50.0, adx=30.0),
            "B": IndicatorSignals(rsi=60.0),
        }
        active = get_active_indicators(universe)

        assert "rsi" in active
        assert "adx" in active
        # Indicators not set on any ticker should be absent.
        assert "iv_rank" not in active

    def test_empty_universe(self) -> None:
        """Empty universe returns empty set."""
        assert get_active_indicators({}) == set()

    def test_all_none_universe(self) -> None:
        """When all tickers have all-None signals, returns empty set."""
        universe = {
            "A": IndicatorSignals(),
            "B": IndicatorSignals(),
        }
        assert get_active_indicators(universe) == set()

    def test_nan_excluded(self) -> None:
        """NaN values are not considered active."""
        universe = {
            "A": IndicatorSignals(rsi=float("nan")),
        }
        active = get_active_indicators(universe)
        assert "rsi" not in active


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end: normalize -> invert -> verify."""

    def test_normalize_then_invert(self) -> None:
        """Inverted indicators are flipped relative to their percentile rank."""
        universe = {
            "WIDE": IndicatorSignals(bb_width=0.10, rsi=80.0),
            "NARROW": IndicatorSignals(bb_width=0.02, rsi=20.0),
        }
        normalized = percentile_rank_normalize(universe)

        # Before inversion: WIDE has higher bb_width -> rank 100.0
        assert _field_val(normalized["WIDE"], "bb_width") == pytest.approx(100.0)
        assert _field_val(normalized["NARROW"], "bb_width") == pytest.approx(0.0)

        inverted = invert_indicators(normalized)

        # After inversion: WIDE (higher raw bb_width = worse) -> 0.0
        assert _field_val(inverted["WIDE"], "bb_width") == pytest.approx(0.0)
        assert _field_val(inverted["NARROW"], "bb_width") == pytest.approx(100.0)

        # Non-inverted RSI remains unchanged.
        assert _field_val(inverted["WIDE"], "rsi") == pytest.approx(100.0)
        assert _field_val(inverted["NARROW"], "rsi") == pytest.approx(0.0)
