"""Unit tests for options_arena.scoring.normalization."""

import pytest

from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.normalization import (
    DOMAIN_BOUNDS,
    INVERTED_INDICATORS,
    get_active_indicators,
    invert_indicators,
    normalize_single_ticker,
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
        """When original 18 fields are populated, each gets a rank; DSE fields stay None."""
        original_fields = [
            "rsi",
            "stochastic_rsi",
            "williams_r",
            "adx",
            "roc",
            "supertrend",
            "atr_pct",
            "bb_width",
            "keltner_width",
            "obv",
            "ad",
            "relative_volume",
            "sma_alignment",
            "vwap_deviation",
            "iv_rank",
            "iv_percentile",
            "put_call_ratio",
            "max_pain_distance",
        ]
        full_signals = IndicatorSignals(**{f: 50.0 for f in original_fields})
        universe = {"ONLY": full_signals}
        result = percentile_rank_normalize(universe)

        for field in original_fields:
            assert _field_val(result["ONLY"], field) == pytest.approx(50.0)

        # DSE fields not set — should remain None after normalization
        dse_fields = [f for f in ALL_FIELDS if f not in original_fields]
        for field in dse_fields:
            assert _field_val(result["ONLY"], field) is None


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
# NaN propagation
# ---------------------------------------------------------------------------


class TestNaNPropagation:
    """Verify graceful handling of NaN, all-NaN, and empty inputs."""

    def test_normalize_all_nan_series(self) -> None:
        """All-NaN input through normalization: every field stays None."""
        universe = {
            "A": IndicatorSignals(rsi=float("nan"), adx=float("nan")),
            "B": IndicatorSignals(rsi=float("nan"), adx=float("nan")),
        }
        result = percentile_rank_normalize(universe)

        # All NaN treated as missing -> None in output
        for ticker in ("A", "B"):
            assert _field_val(result[ticker], "rsi") is None
            assert _field_val(result[ticker], "adx") is None

    def test_normalize_mixed_nan_series(self) -> None:
        """Mixed NaN and valid values: NaN entries get None, valid entries ranked."""
        universe = {
            "NAN1": IndicatorSignals(rsi=float("nan"), adx=50.0),
            "VALID": IndicatorSignals(rsi=50.0, adx=80.0),
            "NAN2": IndicatorSignals(rsi=float("nan"), adx=float("nan")),
            "ALSO_VALID": IndicatorSignals(rsi=80.0, adx=20.0),
        }
        result = percentile_rank_normalize(universe)

        # RSI: only VALID (50.0) and ALSO_VALID (80.0) participate
        assert _field_val(result["NAN1"], "rsi") is None
        assert _field_val(result["NAN2"], "rsi") is None
        assert _field_val(result["VALID"], "rsi") == pytest.approx(0.0)
        assert _field_val(result["ALSO_VALID"], "rsi") == pytest.approx(100.0)

        # ADX: NAN1 (50.0), VALID (80.0), ALSO_VALID (20.0) — NAN2 excluded
        assert _field_val(result["NAN2"], "adx") is None
        assert _field_val(result["ALSO_VALID"], "adx") == pytest.approx(0.0)
        assert _field_val(result["NAN1"], "adx") == pytest.approx(50.0)
        assert _field_val(result["VALID"], "adx") == pytest.approx(100.0)

    def test_normalize_empty_series(self) -> None:
        """Empty universe returns empty dict without error."""
        result = percentile_rank_normalize({})
        assert result == {}

    def test_invert_all_nan_preserves_none(self) -> None:
        """Inversion of all-NaN normalized universe: None values stay None."""
        # Simulate normalization output where all inverted fields are None
        normalized = {
            "A": IndicatorSignals(
                bb_width=None,
                atr_pct=None,
                keltner_width=None,
            ),
        }
        result = invert_indicators(normalized)

        for field in INVERTED_INDICATORS:
            assert _field_val(result["A"], field) is None

    def test_get_active_indicators_all_nan(self) -> None:
        """All-NaN universe returns empty active set."""
        universe = {
            "A": IndicatorSignals(rsi=float("nan"), adx=float("nan")),
            "B": IndicatorSignals(rsi=float("nan"), adx=float("nan")),
        }
        active = get_active_indicators(universe)
        assert "rsi" not in active
        assert "adx" not in active

    def test_get_active_indicators_mixed_nan(self) -> None:
        """Mixed NaN/valid: only fields with at least one finite value are active."""
        universe = {
            "A": IndicatorSignals(rsi=float("nan"), adx=30.0),
            "B": IndicatorSignals(rsi=50.0, adx=float("nan")),
        }
        active = get_active_indicators(universe)
        assert "rsi" in active
        assert "adx" in active
        # Fields not set at all remain inactive
        assert "iv_rank" not in active

    def test_normalize_inf_treated_as_missing(self) -> None:
        """+/-Inf values are excluded like NaN and map to None."""
        universe = {
            "NEG_INF": IndicatorSignals(rsi=float("-inf")),
            "POS_INF": IndicatorSignals(rsi=float("inf")),
            "VALID": IndicatorSignals(rsi=55.0),
        }
        result = percentile_rank_normalize(universe)

        assert _field_val(result["NEG_INF"], "rsi") is None
        assert _field_val(result["POS_INF"], "rsi") is None
        assert _field_val(result["VALID"], "rsi") == pytest.approx(50.0)

    def test_get_active_indicators_inf_excluded(self) -> None:
        """+/-Inf values are not considered active."""
        universe = {
            "A": IndicatorSignals(adx=float("inf")),
            "B": IndicatorSignals(adx=float("-inf")),
        }
        active = get_active_indicators(universe)
        assert "adx" not in active


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


# ---------------------------------------------------------------------------
# normalize_single_ticker
# ---------------------------------------------------------------------------


class TestNormalizeSingleTicker:
    """Tests for normalize_single_ticker() — domain-bound linear scaling."""

    def test_mid_range_values_scale_to_50(self) -> None:
        """Values at domain midpoint produce ~50.0."""
        # RSI domain is [0, 100], midpoint is 50.0 -> scaled 50.0
        # ADX domain is [0, 100], midpoint is 50.0 -> scaled 50.0
        # MACD domain is [-5, 5], midpoint is 0.0 -> scaled 50.0
        signals = IndicatorSignals(rsi=50.0, adx=50.0, macd=0.0)
        result = normalize_single_ticker(signals)

        assert _field_val(result, "rsi") == pytest.approx(50.0)
        assert _field_val(result, "adx") == pytest.approx(50.0)
        assert _field_val(result, "macd") == pytest.approx(50.0)

    def test_min_bound_scales_to_zero(self) -> None:
        """Values at domain minimum produce 0.0."""
        signals = IndicatorSignals(
            rsi=0.0,  # domain [0, 100] -> 0.0
            adx=0.0,  # domain [0, 100] -> 0.0
            macd=-5.0,  # domain [-5, 5] -> 0.0
            williams_r=-100.0,  # domain [-100, 0] -> 0.0
        )
        result = normalize_single_ticker(signals)

        assert _field_val(result, "rsi") == pytest.approx(0.0)
        assert _field_val(result, "adx") == pytest.approx(0.0)
        assert _field_val(result, "macd") == pytest.approx(0.0)
        assert _field_val(result, "williams_r") == pytest.approx(0.0)

    def test_max_bound_scales_to_hundred(self) -> None:
        """Values at domain maximum produce 100.0."""
        signals = IndicatorSignals(
            rsi=100.0,  # domain [0, 100] -> 100.0
            adx=100.0,  # domain [0, 100] -> 100.0
            macd=5.0,  # domain [-5, 5] -> 100.0
            williams_r=0.0,  # domain [-100, 0] -> 100.0
        )
        result = normalize_single_ticker(signals)

        assert _field_val(result, "rsi") == pytest.approx(100.0)
        assert _field_val(result, "adx") == pytest.approx(100.0)
        assert _field_val(result, "macd") == pytest.approx(100.0)
        assert _field_val(result, "williams_r") == pytest.approx(100.0)

    def test_out_of_bounds_clamped(self) -> None:
        """Values beyond domain bounds are clamped to [0, 100]."""
        signals = IndicatorSignals(
            macd=10.0,  # domain [-5, 5], 10.0 is above max -> clamped to 100
            vwap_deviation=-0.5,  # domain [-0.1, 0.1], -0.5 is below min -> clamped to 0
        )
        result = normalize_single_ticker(signals)

        assert _field_val(result, "macd") == pytest.approx(100.0)
        assert _field_val(result, "vwap_deviation") == pytest.approx(0.0)

    def test_none_values_preserved(self) -> None:
        """None indicator values pass through unchanged."""
        signals = IndicatorSignals(rsi=50.0, adx=None, macd=None)
        result = normalize_single_ticker(signals)

        assert _field_val(result, "rsi") == pytest.approx(50.0)
        assert _field_val(result, "adx") is None
        assert _field_val(result, "macd") is None

    def test_inverted_indicators_flipped(self) -> None:
        """bb_width, atr_pct, keltner_width are inverted after scaling."""
        # bb_width domain [0, 0.5], value 0.25 -> scaled 50.0 -> inverted to 50.0
        # bb_width domain [0, 0.5], value 0.0 -> scaled 0.0 -> inverted to 100.0
        # atr_pct domain [0, 0.1], value 0.1 -> scaled 100.0 -> inverted to 0.0
        signals = IndicatorSignals(
            bb_width=0.0,  # scaled 0.0 -> inverted to 100.0
            atr_pct=0.1,  # scaled 100.0 -> inverted to 0.0
            keltner_width=0.25,  # scaled 50.0 -> inverted to 50.0
        )
        result = normalize_single_ticker(signals)

        assert _field_val(result, "bb_width") == pytest.approx(100.0)
        assert _field_val(result, "atr_pct") == pytest.approx(0.0)
        assert _field_val(result, "keltner_width") == pytest.approx(50.0)

    def test_nan_values_preserved(self) -> None:
        """NaN values are passed through (model_validator normalizes to None)."""
        # IndicatorSignals model_validator converts NaN to None
        signals = IndicatorSignals(rsi=float("nan"), adx=30.0)
        result = normalize_single_ticker(signals)

        assert _field_val(result, "rsi") is None
        assert _field_val(result, "adx") == pytest.approx(30.0)

    def test_all_none_passthrough(self) -> None:
        """All-None IndicatorSignals passes through without error."""
        signals = IndicatorSignals()
        result = normalize_single_ticker(signals)

        for field in DOMAIN_BOUNDS:
            assert _field_val(result, field) is None

    def test_domain_bounds_cover_expected_fields(self) -> None:
        """DOMAIN_BOUNDS contains entries for the core 19 indicator fields."""
        expected = {
            "rsi",
            "stochastic_rsi",
            "williams_r",
            "adx",
            "roc",
            "supertrend",
            "macd",
            "bb_width",
            "atr_pct",
            "keltner_width",
            "obv",
            "ad",
            "relative_volume",
            "sma_alignment",
            "vwap_deviation",
            "iv_rank",
            "iv_percentile",
            "put_call_ratio",
            "max_pain_distance",
        }
        assert set(DOMAIN_BOUNDS.keys()) == expected

    def test_fields_not_in_domain_bounds_unchanged(self) -> None:
        """DSE fields not in DOMAIN_BOUNDS pass through without scaling."""
        signals = IndicatorSignals(
            rsi=50.0,
            iv_hv_spread=0.15,  # DSE field, not in DOMAIN_BOUNDS
            gex=500.0,  # DSE field, not in DOMAIN_BOUNDS
        )
        result = normalize_single_ticker(signals)

        # RSI is in DOMAIN_BOUNDS -> scaled
        assert _field_val(result, "rsi") == pytest.approx(50.0)
        # DSE fields not in DOMAIN_BOUNDS -> unchanged
        assert _field_val(result, "iv_hv_spread") == pytest.approx(0.15)
        assert _field_val(result, "gex") == pytest.approx(500.0)
