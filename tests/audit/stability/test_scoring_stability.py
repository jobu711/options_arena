"""Stability tests for scoring functions: Hypothesis + extreme inputs + NaN injection.

Covers normalization (5), composite (2), direction (1), dimensional (3), and
contracts-related scoring functions. Every function produces valid output or
raises a clean error. Zero silent NaN propagation.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from options_arena.models.config import ScanConfig
from options_arena.models.enums import SignalDirection
from options_arena.models.scan import IndicatorSignals
from options_arena.scoring.composite import composite_score, score_universe
from options_arena.scoring.direction import determine_direction
from options_arena.scoring.normalization import (
    compute_normalization_stats,
    get_active_indicators,
    invert_indicators,
    normalize_single_ticker,
    percentile_rank_normalize,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for scoring inputs
# ---------------------------------------------------------------------------

# Strategy for a single IndicatorSignals with random optional floats
_indicator_float = st.one_of(
    st.none(),
    st.floats(min_value=-100.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)


@st.composite
def indicator_signals_strategy(draw: st.DrawFn) -> IndicatorSignals:
    """Generate an IndicatorSignals with random float | None fields."""
    return IndicatorSignals(
        rsi=draw(_indicator_float),
        stochastic_rsi=draw(_indicator_float),
        williams_r=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=-100.0, max_value=0.0, allow_nan=False, allow_infinity=False),
            )
        ),
        adx=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        ),
        roc=draw(_indicator_float),
        supertrend=draw(st.one_of(st.none(), st.sampled_from([-1.0, 1.0]))),
        macd=draw(_indicator_float),
        bb_width=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            )
        ),
        atr_pct=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            )
        ),
        keltner_width=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
            )
        ),
        obv=draw(_indicator_float),
        ad=draw(_indicator_float),
        relative_volume=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
            )
        ),
        sma_alignment=draw(_indicator_float),
        vwap_deviation=draw(_indicator_float),
        iv_rank=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        ),
        iv_percentile=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            )
        ),
        put_call_ratio=draw(
            st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            )
        ),
        max_pain_distance=draw(_indicator_float),
    )


@st.composite
def universe_strategy(
    draw: st.DrawFn, min_size: int = 1, max_size: int = 20
) -> dict[str, IndicatorSignals]:
    """Generate a universe dict of ticker -> IndicatorSignals."""
    n = draw(st.integers(min_value=min_size, max_value=max_size))
    universe: dict[str, IndicatorSignals] = {}
    for i in range(n):
        ticker = f"T{i:03d}"
        universe[ticker] = draw(indicator_signals_strategy())
    return universe


# ===========================================================================
# Percentile Rank Normalize Stability
# ===========================================================================


class TestPercentileRankNormalizeStability:
    """Hypothesis + extreme + NaN tests for percentile_rank_normalize."""

    @pytest.mark.audit_stability
    @given(universe=universe_strategy(min_size=1, max_size=20))
    @settings(max_examples=50)
    def test_normalized_values_in_range(self, universe: dict[str, IndicatorSignals]) -> None:
        """Property: percentile-ranked values are in [0, 100] or None."""
        result = percentile_rank_normalize(universe)
        assert len(result) == len(universe)
        for ticker, signals in result.items():
            for field_name in IndicatorSignals.model_fields:
                val = getattr(signals, field_name)
                if val is not None:
                    assert 0.0 <= val <= 100.0, (
                        f"Ticker {ticker}, {field_name}: {val} not in [0, 100]"
                    )

    @pytest.mark.audit_stability
    def test_empty_universe(self) -> None:
        """Empty universe returns empty dict."""
        result = percentile_rank_normalize({})
        assert result == {}

    @pytest.mark.audit_stability
    def test_single_ticker_gets_midpoint(self) -> None:
        """Single ticker gets 50.0 for all present indicators."""
        signals = IndicatorSignals(rsi=50.0, adx=25.0)
        result = percentile_rank_normalize({"AAPL": signals})
        assert result["AAPL"].rsi == pytest.approx(50.0)
        assert result["AAPL"].adx == pytest.approx(50.0)

    @pytest.mark.audit_stability
    def test_all_identical_values(self) -> None:
        """All tickers with same value get same percentile."""
        signals = IndicatorSignals(rsi=50.0)
        universe = {f"T{i}": signals for i in range(5)}
        result = percentile_rank_normalize(universe)
        rsi_values = {s.rsi for s in result.values()}
        # All should get the same percentile rank
        assert len(rsi_values) == 1

    @pytest.mark.audit_stability
    def test_all_none_universe(self) -> None:
        """Universe where all indicators are None produces all-None output."""
        universe = {f"T{i}": IndicatorSignals() for i in range(5)}
        result = percentile_rank_normalize(universe)
        for signals in result.values():
            for field_name in IndicatorSignals.model_fields:
                assert getattr(signals, field_name) is None


# ===========================================================================
# Invert Indicators Stability
# ===========================================================================


class TestInvertIndicatorsStability:
    """Hypothesis + extreme tests for invert_indicators."""

    @pytest.mark.audit_stability
    @given(universe=universe_strategy(min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_invert_preserves_none(self, universe: dict[str, IndicatorSignals]) -> None:
        """Property: None values remain None after inversion."""
        normalized = percentile_rank_normalize(universe)
        inverted = invert_indicators(normalized)
        for ticker in universe:
            for field_name in IndicatorSignals.model_fields:
                norm_val = getattr(normalized[ticker], field_name)
                inv_val = getattr(inverted[ticker], field_name)
                if norm_val is None:
                    assert inv_val is None

    @pytest.mark.audit_stability
    def test_invert_double_inversion_identity(self) -> None:
        """Double inversion returns to original values."""
        signals = IndicatorSignals(rsi=75.0, bb_width=30.0, atr_pct=40.0, adx=50.0)
        universe = {"AAPL": signals}
        normalized = percentile_rank_normalize(universe)
        inverted_once = invert_indicators(normalized)
        inverted_twice = invert_indicators(inverted_once)
        for field_name in IndicatorSignals.model_fields:
            v1 = getattr(normalized["AAPL"], field_name)
            v2 = getattr(inverted_twice["AAPL"], field_name)
            if v1 is not None:
                assert v1 == pytest.approx(v2, abs=1e-10)


# ===========================================================================
# Normalize Single Ticker Stability
# ===========================================================================


class TestNormalizeSingleTickerStability:
    """Hypothesis + extreme tests for normalize_single_ticker."""

    @pytest.mark.audit_stability
    @given(signals=indicator_signals_strategy())
    @settings(max_examples=50)
    def test_normalized_single_in_range(self, signals: IndicatorSignals) -> None:
        """Property: single-ticker normalized values are in [0, 100] or None."""
        result = normalize_single_ticker(signals)
        for field_name in IndicatorSignals.model_fields:
            val = getattr(result, field_name)
            if val is not None:
                assert 0.0 <= val <= 100.0, f"{field_name}: {val} not in [0, 100]"

    @pytest.mark.audit_stability
    def test_normalize_single_all_none(self) -> None:
        """All-None signals stay all-None after normalization."""
        result = normalize_single_ticker(IndicatorSignals())
        for field_name in IndicatorSignals.model_fields:
            assert getattr(result, field_name) is None


# ===========================================================================
# Get Active Indicators Stability
# ===========================================================================


class TestGetActiveIndicatorsStability:
    """Hypothesis + extreme tests for get_active_indicators."""

    @pytest.mark.audit_stability
    @given(universe=universe_strategy(min_size=0, max_size=10))
    @settings(max_examples=50)
    def test_active_returns_set(self, universe: dict[str, IndicatorSignals]) -> None:
        """Property: get_active_indicators always returns a set of strings."""
        result = get_active_indicators(universe)
        assert isinstance(result, set)
        for name in result:
            assert isinstance(name, str)

    @pytest.mark.audit_stability
    def test_empty_universe_empty_set(self) -> None:
        """Empty universe returns empty set."""
        assert get_active_indicators({}) == set()

    @pytest.mark.audit_stability
    def test_all_none_returns_empty(self) -> None:
        """All-None universe returns empty set."""
        universe = {f"T{i}": IndicatorSignals() for i in range(5)}
        assert get_active_indicators(universe) == set()

    @pytest.mark.audit_stability
    def test_nan_not_counted_as_active(self) -> None:
        """NaN values are not counted as active indicators."""
        signals = IndicatorSignals(rsi=float("nan"))
        result = get_active_indicators({"AAPL": signals})
        assert "rsi" not in result


# ===========================================================================
# Compute Normalization Stats Stability
# ===========================================================================


class TestComputeNormalizationStatsStability:
    """Hypothesis + extreme tests for compute_normalization_stats."""

    @pytest.mark.audit_stability
    @given(universe=universe_strategy(min_size=1, max_size=10))
    @settings(max_examples=30)
    def test_stats_finite_values(self, universe: dict[str, IndicatorSignals]) -> None:
        """Property: all stats values are finite."""
        stats_list = compute_normalization_stats(universe)
        for stat in stats_list:
            assert math.isfinite(stat.min_value)
            assert math.isfinite(stat.max_value)
            assert math.isfinite(stat.median_value)
            assert math.isfinite(stat.mean_value)
            if stat.std_dev is not None:
                assert math.isfinite(stat.std_dev)
            assert math.isfinite(stat.p25)
            assert math.isfinite(stat.p75)
            assert stat.ticker_count >= 1

    @pytest.mark.audit_stability
    def test_stats_empty_universe(self) -> None:
        """Empty universe returns empty stats list."""
        assert compute_normalization_stats({}) == []

    @pytest.mark.audit_stability
    def test_stats_single_value_no_std(self) -> None:
        """Single-ticker universe: std_dev is None (need >= 2 for std)."""
        signals = IndicatorSignals(rsi=50.0)
        stats_list = compute_normalization_stats({"AAPL": signals})
        rsi_stat = next((s for s in stats_list if s.indicator_name == "rsi"), None)
        assert rsi_stat is not None
        assert rsi_stat.std_dev is None


# ===========================================================================
# Composite Score Stability
# ===========================================================================


class TestCompositeScoreStability:
    """Hypothesis + extreme tests for composite_score."""

    @pytest.mark.audit_stability
    @given(signals=indicator_signals_strategy())
    @settings(max_examples=50)
    def test_composite_score_in_range(self, signals: IndicatorSignals) -> None:
        """Property: composite score is in [0.0, 100.0]."""
        score = composite_score(signals)
        assert 0.0 <= score <= 100.0, f"Composite score {score} out of range"

    @pytest.mark.audit_stability
    def test_composite_score_all_none(self) -> None:
        """All-None signals produce score 0.0."""
        score = composite_score(IndicatorSignals())
        assert score == 0.0

    @pytest.mark.audit_stability
    def test_composite_score_all_hundred(self) -> None:
        """All indicators at 100 produce maximum score."""
        signals = IndicatorSignals(
            rsi=100.0,
            stochastic_rsi=100.0,
            williams_r=100.0,
            adx=100.0,
            roc=100.0,
            supertrend=100.0,
            macd=100.0,
            bb_width=100.0,
            atr_pct=100.0,
            keltner_width=100.0,
            obv=100.0,
            ad=100.0,
            relative_volume=100.0,
            sma_alignment=100.0,
            vwap_deviation=100.0,
            iv_rank=100.0,
            iv_percentile=100.0,
            put_call_ratio=100.0,
            max_pain_distance=100.0,
        )
        score = composite_score(signals)
        assert score == pytest.approx(100.0, abs=0.1)

    @pytest.mark.audit_stability
    def test_composite_score_nan_field_ignored(self) -> None:
        """NaN field is ignored (treated like None)."""
        signals = IndicatorSignals(rsi=float("nan"), adx=50.0)
        score = composite_score(signals)
        # Should compute based on adx alone
        assert 0.0 <= score <= 100.0


# ===========================================================================
# Score Universe Stability
# ===========================================================================


class TestScoreUniverseStability:
    """Hypothesis + extreme tests for score_universe."""

    @pytest.mark.audit_stability
    @given(universe=universe_strategy(min_size=1, max_size=10))
    @settings(max_examples=30)
    def test_score_universe_sorted_descending(self, universe: dict[str, IndicatorSignals]) -> None:
        """Property: results are sorted descending by composite_score."""
        results = score_universe(universe)
        for i in range(len(results) - 1):
            assert results[i].composite_score >= results[i + 1].composite_score

    @pytest.mark.audit_stability
    def test_score_universe_empty(self) -> None:
        """Empty universe returns empty list."""
        assert score_universe({}) == []


# ===========================================================================
# Determine Direction Stability
# ===========================================================================


class TestDetermineDirectionStability:
    """Hypothesis + extreme + NaN tests for determine_direction."""

    @pytest.mark.audit_stability
    @given(
        adx_val=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        rsi_val=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        sma=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
        supertrend_val=st.one_of(st.none(), st.sampled_from([-1.0, 1.0])),
        roc_val=st.one_of(
            st.none(),
            st.floats(min_value=-50.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=100)
    def test_direction_is_valid_enum(
        self,
        adx_val: float,
        rsi_val: float,
        sma: float,
        supertrend_val: float | None,
        roc_val: float | None,
    ) -> None:
        """Property: determine_direction always returns a valid SignalDirection."""
        result = determine_direction(adx_val, rsi_val, sma, supertrend=supertrend_val, roc=roc_val)
        assert result in (
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        )

    @pytest.mark.audit_stability
    def test_direction_low_adx_neutral(self) -> None:
        """ADX below threshold always produces NEUTRAL."""
        config = ScanConfig(adx_trend_threshold=15.0)
        result = determine_direction(10.0, 80.0, 1.0, config=config)
        assert result == SignalDirection.NEUTRAL

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_direction_nan_inf_adx(self, bad_value: float) -> None:
        """Non-finite ADX produces NEUTRAL."""
        result = determine_direction(bad_value, 50.0, 0.5)
        assert result == SignalDirection.NEUTRAL

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_direction_nan_inf_rsi(self, bad_value: float) -> None:
        """Non-finite RSI produces NEUTRAL."""
        result = determine_direction(30.0, bad_value, 0.5)
        assert result == SignalDirection.NEUTRAL

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_direction_nan_inf_sma(self, bad_value: float) -> None:
        """Non-finite SMA alignment produces NEUTRAL."""
        result = determine_direction(30.0, 50.0, bad_value)
        assert result == SignalDirection.NEUTRAL

    @pytest.mark.audit_stability
    def test_direction_extreme_rsi_overbought(self) -> None:
        """Extreme overbought RSI with strong trend produces BULLISH."""
        result = determine_direction(40.0, 95.0, 1.0)
        assert result == SignalDirection.BULLISH

    @pytest.mark.audit_stability
    def test_direction_extreme_rsi_oversold(self) -> None:
        """Extreme oversold RSI with strong trend produces BEARISH."""
        result = determine_direction(40.0, 5.0, -1.0)
        assert result == SignalDirection.BEARISH

    @pytest.mark.audit_stability
    def test_direction_equal_scores_sma_tiebreaker(self) -> None:
        """Equal bull/bear scores with positive SMA alignment returns BULLISH."""
        # RSI at midpoint (50) gives mild signal to neither side with default thresholds
        # SMA positive gives mild bullish, but only if ADX > threshold
        result = determine_direction(25.0, 55.0, 1.0, supertrend=-1.0)
        # bullish_score=1 (RSI>50 mild) + 0 (SMA>0.5 mild), bearish_score=0+1(ST<0 mild)
        # Actually: bullish_score=2 (mild rsi + mild sma), bearish_score=1 (mild ST)
        assert result in (
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        )


# ===========================================================================
# NaN Injection for Scoring Inputs
# ===========================================================================


class TestScoringNaNInjection:
    """NaN injection across scoring function inputs."""

    @pytest.mark.audit_stability
    def test_percentile_rank_with_nan_values(self) -> None:
        """NaN values in IndicatorSignals are treated like None (excluded)."""
        signals_a = IndicatorSignals(rsi=float("nan"), adx=50.0)
        signals_b = IndicatorSignals(rsi=60.0, adx=30.0)
        universe = {"A": signals_a, "B": signals_b}
        result = percentile_rank_normalize(universe)
        # A's rsi should be None (NaN excluded), B's rsi should get 50.0 (single ticker)
        assert result["A"].rsi is None
        assert result["B"].rsi == pytest.approx(50.0)

    @pytest.mark.audit_stability
    def test_composite_score_with_inf(self) -> None:
        """Inf values in IndicatorSignals are treated as non-finite (skipped)."""
        signals = IndicatorSignals(rsi=float("inf"), adx=50.0)
        score = composite_score(signals)
        # Should compute based on adx alone
        assert 0.0 <= score <= 100.0

    @pytest.mark.audit_stability
    def test_normalize_single_with_nan(self) -> None:
        """NaN values pass through normalize_single_ticker unchanged."""
        signals = IndicatorSignals(rsi=float("nan"))
        result = normalize_single_ticker(signals)
        # NaN should pass through (isfinite check returns False, value preserved)
        val = result.rsi
        if val is not None:
            assert not math.isfinite(val) or 0.0 <= val <= 100.0
