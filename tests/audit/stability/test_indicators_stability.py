"""Stability tests for indicator functions: Hypothesis + extreme inputs + NaN injection.

Covers oscillators (3), trend (7), volatility (3), volume (3), moving averages (2),
iv_analytics (13), regime (7), options_specific (6), flow_analytics (5),
hv_estimators (3), and vol_surface (2).
Every function produces finite output for valid inputs OR raises InsufficientDataError /
ValueError. NaN in input propagates cleanly (no silent corruption of non-NaN values).
"""

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from options_arena.indicators.flow_analytics import (
    compute_dollar_volume_trend,
    compute_gex,
    compute_max_pain_magnet,
    compute_oi_concentration,
    compute_unusual_activity,
)
from options_arena.indicators.hv_estimators import (
    compute_hv_parkinson,
    compute_hv_rogers_satchell,
    compute_hv_yang_zhang,
)
from options_arena.indicators.iv_analytics import (
    classify_vol_regime,
    compute_call_skew,
    compute_ewma_vol_forecast,
    compute_expected_move,
    compute_expected_move_ratio,
    compute_hv_20d,
    compute_iv_hv_spread,
    compute_iv_term_shape,
    compute_iv_term_slope,
    compute_put_skew,
    compute_skew_ratio,
    compute_vix_correlation,
    compute_vol_cone_pctl,
)
from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.options_specific import (
    compute_max_loss_ratio,
    compute_optimal_dte,
    compute_pop,
    compute_spread_quality,
    put_call_ratio_oi,
    put_call_ratio_volume,
)
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.regime import (
    classify_market_regime,
    compute_correlation_regime_shift,
    compute_risk_on_off,
    compute_rs_vs_spx,
    compute_sector_momentum,
    compute_vix_term_structure,
    compute_volume_profile_skew,
)
from options_arena.indicators.trend import (
    adx,
    compute_adx_exhaustion,
    compute_multi_tf_alignment,
    compute_rsi_divergence,
    macd,
    roc,
    supertrend,
)
from options_arena.indicators.vol_surface import (
    VolSurfaceResult,
    compute_surface_indicators,
    compute_vol_surface,
)
from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume
from options_arena.models.enums import IVTermStructureShape, MarketRegime, OptionType, VolRegime
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# Hypothesis strategies for valid OHLCV DataFrames
# ---------------------------------------------------------------------------


@st.composite
def ohlcv_dataframe(
    draw: st.DrawFn,
    min_rows: int = 50,
    max_rows: int = 300,
) -> pd.DataFrame:
    """Generate a valid OHLCV DataFrame with realistic price relationships.

    Ensures high >= low, close within [low, high], open within [low, high],
    and volume > 0.
    """
    n = draw(st.integers(min_value=min_rows, max_value=max_rows))

    # Generate base prices with a random walk
    base = draw(st.floats(min_value=10.0, max_value=1000.0, allow_nan=False, allow_infinity=False))
    changes = draw(
        st.lists(
            st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    prices = [base]
    for change in changes[1:]:
        prices.append(max(0.1, prices[-1] + change))

    close = np.array(prices[:n], dtype=float)
    # Generate high/low relative to close
    high_offsets = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )
    low_offsets = draw(
        st.lists(
            st.floats(min_value=0.0, max_value=5.0, allow_nan=False, allow_infinity=False),
            min_size=n,
            max_size=n,
        )
    )

    high = np.array([c + abs(h) for c, h in zip(close, high_offsets, strict=True)], dtype=float)
    low = np.array(
        [max(0.01, c - abs(lo)) for c, lo in zip(close, low_offsets, strict=True)],
        dtype=float,
    )
    open_prices = np.array([(h + lo) / 2.0 for h, lo in zip(high, low, strict=True)], dtype=float)
    volume = np.array(
        draw(
            st.lists(
                st.integers(min_value=100, max_value=10_000_000),
                min_size=n,
                max_size=n,
            )
        ),
        dtype=float,
    )

    return pd.DataFrame(
        {"open": open_prices, "high": high, "low": low, "close": close, "volume": volume}
    )


def _make_close_series(n: int, base: float = 100.0) -> pd.Series:
    """Create a simple close price series for non-Hypothesis tests."""
    rng = np.random.default_rng(42)
    changes = rng.normal(0, 1, n)
    prices = np.cumsum(changes) + base
    prices = np.maximum(prices, 0.1)
    return pd.Series(prices, name="close")


def _make_ohlcv_df(n: int, base: float = 100.0) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame for non-Hypothesis tests."""
    rng = np.random.default_rng(42)
    close = np.cumsum(rng.normal(0, 1, n)) + base
    close = np.maximum(close, 0.1)
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = np.maximum(close - np.abs(rng.normal(0, 0.5, n)), 0.01)
    open_p = (high + low) / 2
    volume = rng.integers(1000, 1_000_000, size=n).astype(float)
    return pd.DataFrame(
        {"open": open_p, "high": high, "low": low, "close": close, "volume": volume}
    )


# ===========================================================================
# RSI Stability
# ===========================================================================


class TestRSIStability:
    """Hypothesis + extreme + NaN tests for RSI."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_rsi_bounded(self, data: pd.DataFrame) -> None:
        """Property: RSI output always in [0, 100] after warmup."""
        result = rsi(data["close"])
        valid = result.dropna()
        if not valid.empty:
            assert valid.min() >= -1e-10, f"RSI below 0: {valid.min()}"
            assert valid.max() <= 100.0 + 1e-10, f"RSI above 100: {valid.max()}"

    @pytest.mark.audit_stability
    def test_rsi_all_same_values(self) -> None:
        """Edge case: all-same-values close prices."""
        close = pd.Series([100.0] * 50)
        result = rsi(close)
        valid = result.dropna()
        # With all same values, changes are zero except first diff which is NaN
        # RSI should be 100 (no losses) after warmup
        for val in valid:
            if math.isfinite(val):
                assert 0.0 <= val <= 100.0

    @pytest.mark.audit_stability
    def test_rsi_monotonic_increase(self) -> None:
        """Edge case: monotonically increasing prices. RSI should be 100."""
        close = pd.Series(np.arange(1.0, 51.0))
        result = rsi(close, period=14)
        valid = result.dropna()
        if not valid.empty:
            # All gains, no losses => RSI should be 100
            assert valid.iloc[-1] == pytest.approx(100.0, abs=0.1)

    @pytest.mark.audit_stability
    def test_rsi_monotonic_decrease(self) -> None:
        """Edge case: monotonically decreasing prices. RSI should be near 0."""
        close = pd.Series(np.arange(50.0, 0.0, -1.0))
        result = rsi(close, period=14)
        valid = result.dropna()
        if not valid.empty:
            assert valid.iloc[-1] < 1.0

    @pytest.mark.audit_stability
    def test_rsi_nan_in_input(self) -> None:
        """NaN in close data does not crash."""
        close = _make_close_series(50)
        close.iloc[25] = float("nan")
        result = rsi(close)
        # Should produce some output, NaN may propagate but no crash
        assert len(result) == len(close)

    @pytest.mark.audit_stability
    def test_rsi_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            rsi(close, period=14)


# ===========================================================================
# Stochastic RSI Stability
# ===========================================================================


class TestStochRSIStability:
    """Hypothesis + extreme + NaN tests for Stochastic RSI."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_stoch_rsi_bounded(self, data: pd.DataFrame) -> None:
        """Property: Stochastic RSI output in [0, 100] after warmup."""
        result = stoch_rsi(data["close"])
        valid = result.dropna()
        if not valid.empty:
            assert valid.min() >= -1e-10, f"Stoch RSI below 0: {valid.min()}"
            assert valid.max() <= 100.0 + 1e-10, f"Stoch RSI above 100: {valid.max()}"

    @pytest.mark.audit_stability
    def test_stoch_rsi_all_same_values(self) -> None:
        """Edge case: all-same-values produces midpoint (50) or valid output."""
        close = pd.Series([100.0] * 50)
        result = stoch_rsi(close)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert 0.0 <= val <= 100.0

    @pytest.mark.audit_stability
    def test_stoch_rsi_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 10)
        with pytest.raises(InsufficientDataError):
            stoch_rsi(close)


# ===========================================================================
# Williams %R Stability
# ===========================================================================


class TestWilliamsRStability:
    """Hypothesis + extreme + NaN tests for Williams %R."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_williams_r_bounded(self, data: pd.DataFrame) -> None:
        """Property: Williams %R output in [-100, 0] after warmup."""
        result = williams_r(data["high"], data["low"], data["close"])
        valid = result.dropna()
        if not valid.empty:
            assert valid.min() >= -100.0 - 1e-10, f"Williams %R below -100: {valid.min()}"
            assert valid.max() <= 0.0 + 1e-10, f"Williams %R above 0: {valid.max()}"

    @pytest.mark.audit_stability
    def test_williams_r_flat_data(self) -> None:
        """Edge case: all high == low == close produces -50 (flat data guard)."""
        n = 30
        series = pd.Series([100.0] * n)
        result = williams_r(series, series, series)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(-50.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_williams_r_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            williams_r(s, s, s, period=14)


# ===========================================================================
# ROC Stability
# ===========================================================================


class TestROCStability:
    """Hypothesis + extreme + NaN tests for Rate of Change."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_roc_finite_after_warmup(self, data: pd.DataFrame) -> None:
        """Property: ROC output is finite after warmup."""
        result = roc(data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"ROC not finite: {val}"

    @pytest.mark.audit_stability
    def test_roc_all_same_values(self) -> None:
        """Edge case: all-same-values produces 0% change."""
        close = pd.Series([100.0] * 30)
        result = roc(close, period=12)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_roc_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            roc(close, period=12)


# ===========================================================================
# ADX Stability
# ===========================================================================


class TestADXStability:
    """Hypothesis + extreme + NaN tests for ADX."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_adx_non_negative_after_warmup(self, data: pd.DataFrame) -> None:
        """Property: ADX is >= 0 after warmup."""
        result = adx(data["high"], data["low"], data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                if math.isfinite(val):
                    assert val >= -1e-10, f"ADX negative: {val}"

    @pytest.mark.audit_stability
    def test_adx_all_same_values(self) -> None:
        """Edge case: all-same-values (no directional movement)."""
        n = 50
        s = pd.Series([100.0] * n)
        result = adx(s, s, s)
        # Should not crash; values after warmup should be finite or NaN
        assert len(result) == n

    @pytest.mark.audit_stability
    def test_adx_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 10)
        with pytest.raises(InsufficientDataError):
            adx(s, s, s, period=14)


# ===========================================================================
# Supertrend Stability
# ===========================================================================


class TestSupertrendStability:
    """Hypothesis + extreme + NaN tests for Supertrend."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_supertrend_values(self, data: pd.DataFrame) -> None:
        """Property: Supertrend outputs +1 or -1 after warmup."""
        result = supertrend(data["high"], data["low"], data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert val in (1.0, -1.0), f"Supertrend unexpected value: {val}"

    @pytest.mark.audit_stability
    def test_supertrend_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            supertrend(s, s, s, period=10)


# ===========================================================================
# MACD Stability
# ===========================================================================


class TestMACDStability:
    """Hypothesis + extreme + NaN tests for MACD."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_macd_finite_after_warmup(self, data: pd.DataFrame) -> None:
        """Property: MACD histogram is finite after warmup."""
        result = macd(data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"MACD not finite: {val}"

    @pytest.mark.audit_stability
    def test_macd_all_same_values(self) -> None:
        """Edge case: all-same-values produces near-zero histogram."""
        close = pd.Series([100.0] * 50)
        result = macd(close)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert abs(val) < 1e-6

    @pytest.mark.audit_stability
    def test_macd_all_nan_input(self) -> None:
        """All-NaN input raises InsufficientDataError."""
        close = pd.Series([float("nan")] * 50)
        with pytest.raises(InsufficientDataError):
            macd(close)

    @pytest.mark.audit_stability
    def test_macd_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 10)
        with pytest.raises(InsufficientDataError):
            macd(close)


# ===========================================================================
# Trend Extension Stability (compute_multi_tf_alignment, etc.)
# ===========================================================================


class TestTrendExtensionStability:
    """Stability tests for trend extension functions."""

    @pytest.mark.audit_stability
    def test_multi_tf_alignment_valid(self) -> None:
        """Valid inputs produce -1.0, 0.0, or 1.0, or None."""
        daily_st = pd.Series([1.0] * 30)
        weekly_close = _make_close_series(20)
        result = compute_multi_tf_alignment(daily_st, weekly_close)
        assert result in (1.0, -1.0, 0.0, None)

    @pytest.mark.audit_stability
    def test_multi_tf_alignment_empty(self) -> None:
        """Empty inputs return None."""
        assert compute_multi_tf_alignment(pd.Series(dtype=float), pd.Series(dtype=float)) is None

    @pytest.mark.audit_stability
    def test_rsi_divergence_valid(self) -> None:
        """Valid inputs produce -1.0, 0.0, 1.0, or None."""
        close = _make_close_series(50)
        rsi_vals = rsi(close)
        result = compute_rsi_divergence(close, rsi_vals)
        assert result in (1.0, -1.0, 0.0, None)

    @pytest.mark.audit_stability
    def test_rsi_divergence_insufficient_data(self) -> None:
        """Insufficient data returns None."""
        close = pd.Series([100.0] * 5)
        rsi_vals = pd.Series([50.0] * 5)
        result = compute_rsi_divergence(close, rsi_vals)
        assert result is None

    @pytest.mark.audit_stability
    def test_adx_exhaustion_valid(self) -> None:
        """Valid inputs produce 0.0 or 1.0, or None."""
        adx_series = pd.Series([45.0, 43.0, 42.0])
        result = compute_adx_exhaustion(adx_series)
        assert result in (0.0, 1.0, None)

    @pytest.mark.audit_stability
    def test_adx_exhaustion_declining_above_threshold(self) -> None:
        """ADX above 40 and declining produces 1.0."""
        adx_series = pd.Series([42.0, 41.0])
        result = compute_adx_exhaustion(adx_series)
        assert result == 1.0

    @pytest.mark.audit_stability
    def test_adx_exhaustion_nan(self) -> None:
        """NaN at latest bar returns None."""
        adx_series = pd.Series([45.0, float("nan")])
        result = compute_adx_exhaustion(adx_series)
        assert result is None

    @pytest.mark.audit_stability
    def test_adx_exhaustion_insufficient(self) -> None:
        """Single-element series returns None."""
        result = compute_adx_exhaustion(pd.Series([50.0]))
        assert result is None


# ===========================================================================
# Bollinger Band Width Stability
# ===========================================================================


class TestBBWidthStability:
    """Hypothesis + extreme + NaN tests for Bollinger Band width."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_bb_width_non_negative(self, data: pd.DataFrame) -> None:
        """Property: BB width >= 0 after warmup."""
        result = bb_width(data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                if math.isfinite(val):
                    assert val >= -1e-10, f"BB width negative: {val}"

    @pytest.mark.audit_stability
    def test_bb_width_all_same_values(self) -> None:
        """Edge case: all-same-values produces zero width."""
        close = pd.Series([100.0] * 30)
        result = bb_width(close, period=20)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_bb_width_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            bb_width(close, period=20)


# ===========================================================================
# ATR Percent Stability
# ===========================================================================


class TestATRPercentStability:
    """Hypothesis + extreme + NaN tests for ATR%."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_atr_percent_non_negative(self, data: pd.DataFrame) -> None:
        """Property: ATR% >= 0 after warmup."""
        result = atr_percent(data["high"], data["low"], data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                if math.isfinite(val):
                    assert val >= -1e-10, f"ATR% negative: {val}"

    @pytest.mark.audit_stability
    def test_atr_percent_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            atr_percent(s, s, s, period=14)


# ===========================================================================
# Keltner Width Stability
# ===========================================================================


class TestKeltnerWidthStability:
    """Hypothesis + extreme + NaN tests for Keltner Channel Width."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_keltner_width_finite(self, data: pd.DataFrame) -> None:
        """Property: Keltner width is finite after warmup."""
        result = keltner_width(data["high"], data["low"], data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"Keltner width not finite: {val}"

    @pytest.mark.audit_stability
    def test_keltner_width_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        with pytest.raises(InsufficientDataError):
            keltner_width(s, s, s, period=20)


# ===========================================================================
# OBV Trend Stability
# ===========================================================================


class TestOBVTrendStability:
    """Hypothesis + extreme + NaN tests for OBV trend (slope)."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_obv_trend_finite(self, data: pd.DataFrame) -> None:
        """Property: OBV trend is finite after warmup."""
        result = obv_trend(data["close"], data["volume"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"OBV trend not finite: {val}"

    @pytest.mark.audit_stability
    def test_obv_trend_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        v = pd.Series([1000.0] * 5)
        with pytest.raises(InsufficientDataError):
            obv_trend(s, v, slope_period=20)


# ===========================================================================
# Relative Volume Stability
# ===========================================================================


class TestRelativeVolumeStability:
    """Hypothesis + extreme + NaN tests for relative volume."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=30, max_rows=250))
    @settings(max_examples=50)
    def test_relative_volume_non_negative(self, data: pd.DataFrame) -> None:
        """Property: relative volume >= 0 after warmup."""
        result = relative_volume(data["volume"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                if math.isfinite(val):
                    assert val >= -1e-10, f"Relative volume negative: {val}"

    @pytest.mark.audit_stability
    def test_relative_volume_all_same(self) -> None:
        """Edge case: all-same-volume produces 1.0 relative volume."""
        vol = pd.Series([1000.0] * 30)
        result = relative_volume(vol, period=20)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(1.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_relative_volume_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        vol = pd.Series([1000.0] * 5)
        with pytest.raises(InsufficientDataError):
            relative_volume(vol, period=20)


# ===========================================================================
# A/D Trend Stability
# ===========================================================================


class TestADTrendStability:
    """Hypothesis + extreme + NaN tests for A/D trend (slope)."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=50, max_rows=250))
    @settings(max_examples=50)
    def test_ad_trend_finite(self, data: pd.DataFrame) -> None:
        """Property: A/D trend is finite after warmup."""
        result = ad_trend(data["high"], data["low"], data["close"], data["volume"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"A/D trend not finite: {val}"

    @pytest.mark.audit_stability
    def test_ad_trend_flat_data(self) -> None:
        """Edge case: high == low == close (CLV = 0)."""
        n = 50
        s = pd.Series([100.0] * n)
        vol = pd.Series([1000.0] * n)
        result = ad_trend(s, s, s, vol)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.audit_stability
    def test_ad_trend_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        s = pd.Series([100.0] * 5)
        v = pd.Series([1000.0] * 5)
        with pytest.raises(InsufficientDataError):
            ad_trend(s, s, s, v, slope_period=20)


# ===========================================================================
# SMA Alignment Stability
# ===========================================================================


class TestSMAAlignmentStability:
    """Hypothesis + extreme + NaN tests for SMA alignment."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=210, max_rows=300))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.large_base_example])
    def test_sma_alignment_finite(self, data: pd.DataFrame) -> None:
        """Property: SMA alignment is finite after warmup."""
        result = sma_alignment(data["close"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"SMA alignment not finite: {val}"

    @pytest.mark.audit_stability
    def test_sma_alignment_all_same_values(self) -> None:
        """Edge case: all-same-values produces zero alignment."""
        close = pd.Series([100.0] * 210)
        result = sma_alignment(close)
        valid = result.dropna()
        for val in valid:
            if math.isfinite(val):
                assert val == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_sma_alignment_insufficient_data(self) -> None:
        """Insufficient data raises InsufficientDataError."""
        close = pd.Series([100.0] * 100)
        with pytest.raises(InsufficientDataError):
            sma_alignment(close)


# ===========================================================================
# VWAP Deviation Stability
# ===========================================================================


class TestVWAPDeviationStability:
    """Hypothesis + extreme + NaN tests for VWAP deviation."""

    @pytest.mark.audit_stability
    @given(data=ohlcv_dataframe(min_rows=10, max_rows=250))
    @settings(max_examples=50)
    def test_vwap_deviation_finite(self, data: pd.DataFrame) -> None:
        """Property: VWAP deviation is finite where volume > 0."""
        result = vwap_deviation(data["close"], data["volume"])
        valid = result.dropna()
        if not valid.empty:
            for val in valid:
                assert math.isfinite(val), f"VWAP deviation not finite: {val}"

    @pytest.mark.audit_stability
    def test_vwap_deviation_zero_volume(self) -> None:
        """Edge case: all-zero volume produces NaN (not crash)."""
        close = pd.Series([100.0] * 10)
        vol = pd.Series([0.0] * 10)
        result = vwap_deviation(close, vol)
        # Should produce NaN for all entries (division by zero guard)
        assert len(result) == 10

    @pytest.mark.audit_stability
    def test_vwap_deviation_insufficient_data(self) -> None:
        """Empty input raises InsufficientDataError."""
        with pytest.raises(InsufficientDataError):
            vwap_deviation(pd.Series(dtype=float), pd.Series(dtype=float))


# ===========================================================================
# IV Analytics Stability (13 functions)
# ===========================================================================


class TestComputeIVHVSpreadStability:
    """Stability tests for compute_iv_hv_spread."""

    @pytest.mark.audit_stability
    def test_iv_hv_spread_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_iv_hv_spread(0.30, 0.25)
        assert result is not None
        assert math.isfinite(result)
        assert result == pytest.approx(0.05, abs=1e-10)

    @pytest.mark.audit_stability
    def test_iv_hv_spread_none_inputs(self) -> None:
        """None inputs return None."""
        assert compute_iv_hv_spread(None, 0.25) is None
        assert compute_iv_hv_spread(0.30, None) is None
        assert compute_iv_hv_spread(None, None) is None

    @pytest.mark.audit_stability
    def test_iv_hv_spread_nan_inputs(self) -> None:
        """NaN inputs return None."""
        assert compute_iv_hv_spread(float("nan"), 0.25) is None
        assert compute_iv_hv_spread(0.30, float("nan")) is None

    @pytest.mark.audit_stability
    def test_iv_hv_spread_inf_inputs(self) -> None:
        """Inf inputs return None."""
        assert compute_iv_hv_spread(float("inf"), 0.25) is None


class TestComputeHV20dStability:
    """Stability tests for compute_hv_20d."""

    @pytest.mark.audit_stability
    def test_hv_20d_valid(self) -> None:
        """Valid close series produces finite non-negative result."""
        close = _make_close_series(50)
        result = compute_hv_20d(close)
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_hv_20d_insufficient_data(self) -> None:
        """Insufficient data returns None."""
        close = pd.Series([100.0] * 10)
        assert compute_hv_20d(close) is None

    @pytest.mark.audit_stability
    def test_hv_20d_flat_data(self) -> None:
        """Flat data produces near-zero HV."""
        close = pd.Series([100.0] * 25)
        result = compute_hv_20d(close)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_hv_20d_nan_in_series(self) -> None:
        """NaN in series does not crash."""
        close = _make_close_series(50)
        close.iloc[25] = float("nan")
        # May return None or finite — no crash
        result = compute_hv_20d(close)
        assert result is None or math.isfinite(result)


class TestComputeIVTermSlopeStability:
    """Stability tests for compute_iv_term_slope."""

    @pytest.mark.audit_stability
    def test_iv_term_slope_contango(self) -> None:
        """Higher 60d IV produces positive slope."""
        result = compute_iv_term_slope(0.35, 0.30)
        assert result is not None
        assert result > 0.0

    @pytest.mark.audit_stability
    def test_iv_term_slope_none(self) -> None:
        """None inputs return None."""
        assert compute_iv_term_slope(None, 0.30) is None
        assert compute_iv_term_slope(0.35, None) is None

    @pytest.mark.audit_stability
    def test_iv_term_slope_zero_denominator(self) -> None:
        """Zero iv_30d returns None."""
        assert compute_iv_term_slope(0.35, 0.0) is None

    @pytest.mark.audit_stability
    def test_iv_term_slope_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_iv_term_slope(float("nan"), 0.30) is None


class TestComputeIVTermShapeStability:
    """Stability tests for compute_iv_term_shape."""

    @pytest.mark.audit_stability
    def test_iv_term_shape_contango(self) -> None:
        """Positive slope returns CONTANGO."""
        result = compute_iv_term_shape(0.10)
        assert result == IVTermStructureShape.CONTANGO

    @pytest.mark.audit_stability
    def test_iv_term_shape_backwardation(self) -> None:
        """Negative slope returns BACKWARDATION."""
        result = compute_iv_term_shape(-0.10)
        assert result == IVTermStructureShape.BACKWARDATION

    @pytest.mark.audit_stability
    def test_iv_term_shape_flat(self) -> None:
        """Near-zero slope returns FLAT."""
        result = compute_iv_term_shape(0.01)
        assert result == IVTermStructureShape.FLAT

    @pytest.mark.audit_stability
    def test_iv_term_shape_none(self) -> None:
        """None input returns None."""
        assert compute_iv_term_shape(None) is None

    @pytest.mark.audit_stability
    def test_iv_term_shape_nan(self) -> None:
        """NaN input returns None."""
        assert compute_iv_term_shape(float("nan")) is None


class TestComputePutSkewStability:
    """Stability tests for compute_put_skew."""

    @pytest.mark.audit_stability
    def test_put_skew_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_put_skew(0.35, 0.30)
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_put_skew_none(self) -> None:
        """None inputs return None."""
        assert compute_put_skew(None, 0.30) is None
        assert compute_put_skew(0.35, None) is None

    @pytest.mark.audit_stability
    def test_put_skew_zero_atm(self) -> None:
        """Zero ATM IV returns None."""
        assert compute_put_skew(0.35, 0.0) is None

    @pytest.mark.audit_stability
    def test_put_skew_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_put_skew(float("nan"), 0.30) is None


class TestComputeCallSkewStability:
    """Stability tests for compute_call_skew."""

    @pytest.mark.audit_stability
    def test_call_skew_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_call_skew(0.28, 0.30)
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_call_skew_none(self) -> None:
        """None inputs return None."""
        assert compute_call_skew(None, 0.30) is None

    @pytest.mark.audit_stability
    def test_call_skew_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_call_skew(float("nan"), 0.30) is None


class TestComputeSkewRatioStability:
    """Stability tests for compute_skew_ratio."""

    @pytest.mark.audit_stability
    def test_skew_ratio_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        result = compute_skew_ratio(0.35, 0.28)
        assert result is not None
        assert math.isfinite(result)
        assert result > 0.0

    @pytest.mark.audit_stability
    def test_skew_ratio_none(self) -> None:
        """None inputs return None."""
        assert compute_skew_ratio(None, 0.28) is None
        assert compute_skew_ratio(0.35, None) is None

    @pytest.mark.audit_stability
    def test_skew_ratio_zero_call(self) -> None:
        """Zero call IV returns None."""
        assert compute_skew_ratio(0.35, 0.0) is None

    @pytest.mark.audit_stability
    def test_skew_ratio_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_skew_ratio(float("nan"), 0.28) is None


class TestClassifyVolRegimeStability:
    """Stability tests for classify_vol_regime."""

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "iv_rank,expected",
        [
            (10.0, VolRegime.LOW),
            (30.0, VolRegime.NORMAL),
            (60.0, VolRegime.ELEVATED),
            (80.0, VolRegime.EXTREME),
        ],
    )
    def test_vol_regime_classification(self, iv_rank: float, expected: VolRegime) -> None:
        """Each IV rank maps to the correct regime."""
        assert classify_vol_regime(iv_rank) == expected

    @pytest.mark.audit_stability
    def test_vol_regime_none(self) -> None:
        """None input returns None."""
        assert classify_vol_regime(None) is None

    @pytest.mark.audit_stability
    def test_vol_regime_nan(self) -> None:
        """NaN input returns None."""
        assert classify_vol_regime(float("nan")) is None


class TestComputeEWMAVolForecastStability:
    """Stability tests for compute_ewma_vol_forecast."""

    @pytest.mark.audit_stability
    def test_ewma_valid(self) -> None:
        """Valid returns produce finite non-negative result."""
        close = _make_close_series(50)
        returns = np.log(close / close.shift(1)).dropna()
        result = compute_ewma_vol_forecast(returns)
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_ewma_insufficient_data(self) -> None:
        """Insufficient data returns None."""
        returns = pd.Series([0.01] * 5)
        assert compute_ewma_vol_forecast(returns) is None

    @pytest.mark.audit_stability
    def test_ewma_invalid_lambda(self) -> None:
        """Invalid lambda returns None."""
        returns = pd.Series([0.01] * 30)
        assert compute_ewma_vol_forecast(returns, lambda_=0.0) is None
        assert compute_ewma_vol_forecast(returns, lambda_=1.0) is None

    @pytest.mark.audit_stability
    def test_ewma_nan_returns(self) -> None:
        """NaN in returns does not crash."""
        returns = pd.Series([0.01] * 30)
        returns.iloc[15] = float("nan")
        result = compute_ewma_vol_forecast(returns)
        assert result is None or math.isfinite(result)


class TestComputeVolConePctlStability:
    """Stability tests for compute_vol_cone_pctl."""

    @pytest.mark.audit_stability
    def test_vol_cone_valid(self) -> None:
        """Valid inputs produce result in [0, 100]."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 50))
        result = compute_vol_cone_pctl(0.30, hv_history)
        assert result is not None
        assert 0.0 <= result <= 100.0

    @pytest.mark.audit_stability
    def test_vol_cone_none_hv(self) -> None:
        """None hv_20d returns None."""
        assert compute_vol_cone_pctl(None, pd.Series([0.20] * 20)) is None

    @pytest.mark.audit_stability
    def test_vol_cone_insufficient_history(self) -> None:
        """Short history returns None."""
        assert compute_vol_cone_pctl(0.30, pd.Series([0.20] * 5)) is None

    @pytest.mark.audit_stability
    def test_vol_cone_nan(self) -> None:
        """NaN hv_20d returns None."""
        assert compute_vol_cone_pctl(float("nan"), pd.Series([0.20] * 20)) is None


class TestComputeVixCorrelationStability:
    """Stability tests for compute_vix_correlation."""

    @pytest.mark.audit_stability
    def test_vix_correlation_valid(self) -> None:
        """Valid inputs produce result in [-1, 1]."""
        rng = np.random.default_rng(42)
        ticker_returns = pd.Series(rng.normal(0, 0.01, 80))
        vix_changes = pd.Series(-ticker_returns + rng.normal(0, 0.005, 80))
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is not None
        assert -1.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_vix_correlation_insufficient_data(self) -> None:
        """Short series returns None."""
        assert compute_vix_correlation(pd.Series([0.01] * 30), pd.Series([0.01] * 30)) is None

    @pytest.mark.audit_stability
    def test_vix_correlation_mismatched_length(self) -> None:
        """Mismatched lengths return None."""
        assert compute_vix_correlation(pd.Series([0.01] * 60), pd.Series([0.01] * 61)) is None


class TestComputeExpectedMoveStability:
    """Stability tests for compute_expected_move."""

    @pytest.mark.audit_stability
    def test_expected_move_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        result = compute_expected_move(150.0, 0.30, 30)
        assert result is not None
        assert math.isfinite(result)
        assert result > 0.0

    @pytest.mark.audit_stability
    def test_expected_move_none_iv(self) -> None:
        """None IV returns None."""
        assert compute_expected_move(150.0, None, 30) is None

    @pytest.mark.audit_stability
    def test_expected_move_zero_dte(self) -> None:
        """Zero DTE returns None."""
        assert compute_expected_move(150.0, 0.30, 0) is None

    @pytest.mark.audit_stability
    def test_expected_move_nan(self) -> None:
        """NaN spot returns None."""
        assert compute_expected_move(float("nan"), 0.30, 30) is None

    @pytest.mark.audit_stability
    def test_expected_move_zero_spot(self) -> None:
        """Zero spot returns None."""
        assert compute_expected_move(0.0, 0.30, 30) is None


class TestComputeExpectedMoveRatioStability:
    """Stability tests for compute_expected_move_ratio."""

    @pytest.mark.audit_stability
    def test_expected_move_ratio_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_expected_move_ratio(5.0, 4.0)
        assert result is not None
        assert math.isfinite(result)
        assert result == pytest.approx(1.25, abs=1e-10)

    @pytest.mark.audit_stability
    def test_expected_move_ratio_none(self) -> None:
        """None inputs return None."""
        assert compute_expected_move_ratio(None, 4.0) is None
        assert compute_expected_move_ratio(5.0, None) is None

    @pytest.mark.audit_stability
    def test_expected_move_ratio_zero_actual(self) -> None:
        """Zero actual move returns None."""
        assert compute_expected_move_ratio(5.0, 0.0) is None

    @pytest.mark.audit_stability
    def test_expected_move_ratio_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_expected_move_ratio(float("nan"), 4.0) is None


# ===========================================================================
# Regime Stability (7 functions)
# ===========================================================================


class TestClassifyMarketRegimeStability:
    """Stability tests for classify_market_regime."""

    @pytest.mark.audit_stability
    def test_crisis_regime(self) -> None:
        """VIX >= 35 produces CRISIS."""
        assert classify_market_regime(40.0, 25.0, 0.0, 0.0) == MarketRegime.CRISIS

    @pytest.mark.audit_stability
    def test_volatile_regime(self) -> None:
        """VIX significantly above SMA produces VOLATILE."""
        assert classify_market_regime(30.0, 20.0, 0.0, 0.0) == MarketRegime.VOLATILE

    @pytest.mark.audit_stability
    def test_trending_regime(self) -> None:
        """Strong directional SPX produces TRENDING."""
        assert classify_market_regime(18.0, 17.0, 0.05, 0.1) == MarketRegime.TRENDING

    @pytest.mark.audit_stability
    def test_mean_reverting_regime(self) -> None:
        """Default case produces MEAN_REVERTING."""
        assert classify_market_regime(15.0, 16.0, 0.01, 0.0) == MarketRegime.MEAN_REVERTING

    @pytest.mark.audit_stability
    def test_market_regime_nan(self) -> None:
        """NaN inputs produce MEAN_REVERTING (safe default)."""
        assert classify_market_regime(float("nan"), 20.0, 0.0, 0.0) == MarketRegime.MEAN_REVERTING


class TestComputeVixTermStructureStability:
    """Stability tests for compute_vix_term_structure."""

    @pytest.mark.audit_stability
    def test_vix_term_structure_contango(self) -> None:
        """VIX3M > VIX produces positive value."""
        result = compute_vix_term_structure(20.0, 22.0)
        assert result is not None
        assert result > 0.0

    @pytest.mark.audit_stability
    def test_vix_term_structure_none(self) -> None:
        """None VIX3M returns None."""
        assert compute_vix_term_structure(20.0, None) is None

    @pytest.mark.audit_stability
    def test_vix_term_structure_zero_vix(self) -> None:
        """Zero VIX returns None."""
        assert compute_vix_term_structure(0.0, 22.0) is None

    @pytest.mark.audit_stability
    def test_vix_term_structure_nan(self) -> None:
        """NaN VIX returns None."""
        assert compute_vix_term_structure(float("nan"), 22.0) is None


class TestComputeRiskOnOffStability:
    """Stability tests for compute_risk_on_off."""

    @pytest.mark.audit_stability
    def test_risk_on_off_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_risk_on_off(0.02, 0.01)
        assert result is not None
        assert math.isfinite(result)
        assert result == pytest.approx(0.01, abs=1e-10)

    @pytest.mark.audit_stability
    def test_risk_on_off_none(self) -> None:
        """None inputs return None."""
        assert compute_risk_on_off(None, 0.01) is None
        assert compute_risk_on_off(0.02, None) is None

    @pytest.mark.audit_stability
    def test_risk_on_off_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_risk_on_off(float("nan"), 0.01) is None


class TestComputeSectorMomentumStability:
    """Stability tests for compute_sector_momentum."""

    @pytest.mark.audit_stability
    def test_sector_momentum_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_sector_momentum(0.05, 0.03)
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_sector_momentum_none(self) -> None:
        """None sector return returns None."""
        assert compute_sector_momentum(None, 0.03) is None

    @pytest.mark.audit_stability
    def test_sector_momentum_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_sector_momentum(float("nan"), 0.03) is None


class TestComputeRSVsSPXStability:
    """Stability tests for compute_rs_vs_spx."""

    @pytest.mark.audit_stability
    def test_rs_vs_spx_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        rng = np.random.default_rng(42)
        ticker_returns = pd.Series(rng.normal(0.001, 0.01, 80))
        spx_returns = pd.Series(rng.normal(0.0005, 0.01, 80))
        result = compute_rs_vs_spx(ticker_returns, spx_returns)
        assert result is not None
        assert math.isfinite(result)
        assert result > 0.0

    @pytest.mark.audit_stability
    def test_rs_vs_spx_insufficient_data(self) -> None:
        """Short series returns None."""
        result = compute_rs_vs_spx(pd.Series([0.01] * 30), pd.Series([0.01] * 30))
        assert result is None

    @pytest.mark.audit_stability
    def test_rs_vs_spx_mismatched_length(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            compute_rs_vs_spx(pd.Series([0.01] * 60), pd.Series([0.01] * 61))


class TestComputeCorrelationRegimeShiftStability:
    """Stability tests for compute_correlation_regime_shift."""

    @pytest.mark.audit_stability
    def test_correlation_regime_shift_valid(self) -> None:
        """Valid inputs produce finite result in [-2, 2]."""
        rng = np.random.default_rng(42)
        ticker = pd.Series(rng.normal(0, 0.01, 80))
        spx = pd.Series(rng.normal(0, 0.01, 80))
        result = compute_correlation_regime_shift(ticker, spx)
        assert result is not None
        assert math.isfinite(result)
        assert -2.0 <= result <= 2.0

    @pytest.mark.audit_stability
    def test_correlation_regime_shift_insufficient(self) -> None:
        """Short series returns None."""
        result = compute_correlation_regime_shift(pd.Series([0.01] * 30), pd.Series([0.01] * 30))
        assert result is None

    @pytest.mark.audit_stability
    def test_correlation_regime_shift_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            compute_correlation_regime_shift(pd.Series([0.01] * 60), pd.Series([0.01] * 61))


class TestComputeVolumeProfileSkewStability:
    """Stability tests for compute_volume_profile_skew."""

    @pytest.mark.audit_stability
    def test_volume_profile_skew_valid(self) -> None:
        """Valid inputs produce finite result."""
        df = _make_ohlcv_df(30)
        result = compute_volume_profile_skew(df["close"], df["volume"])
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_volume_profile_skew_insufficient(self) -> None:
        """Short series returns None."""
        result = compute_volume_profile_skew(pd.Series([100.0] * 5), pd.Series([1000.0] * 5))
        assert result is None

    @pytest.mark.audit_stability
    def test_volume_profile_skew_zero_volume(self) -> None:
        """All-zero volume returns None."""
        result = compute_volume_profile_skew(pd.Series([100.0] * 25), pd.Series([0.0] * 25))
        assert result is None

    @pytest.mark.audit_stability
    def test_volume_profile_skew_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            compute_volume_profile_skew(pd.Series([100.0] * 20), pd.Series([1000.0] * 21))


# ===========================================================================
# Options Specific Stability (6 missing functions)
# ===========================================================================


class TestPutCallRatioVolumeStability:
    """Stability tests for put_call_ratio_volume."""

    @pytest.mark.audit_stability
    def test_pcr_volume_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        result = put_call_ratio_volume(500, 1000)
        assert math.isfinite(result)
        assert result == pytest.approx(0.5, abs=1e-10)

    @pytest.mark.audit_stability
    def test_pcr_volume_zero_calls(self) -> None:
        """Zero call volume returns NaN."""
        result = put_call_ratio_volume(500, 0)
        assert math.isnan(result)


class TestPutCallRatioOIStability:
    """Stability tests for put_call_ratio_oi."""

    @pytest.mark.audit_stability
    def test_pcr_oi_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        result = put_call_ratio_oi(600, 1000)
        assert math.isfinite(result)
        assert result == pytest.approx(0.6, abs=1e-10)

    @pytest.mark.audit_stability
    def test_pcr_oi_zero_calls(self) -> None:
        """Zero call OI returns NaN."""
        result = put_call_ratio_oi(600, 0)
        assert math.isnan(result)


class TestComputePopStability:
    """Stability tests for compute_pop."""

    @pytest.mark.audit_stability
    def test_pop_call_valid(self) -> None:
        """Valid d2 for call produces result in [0, 1]."""
        result = compute_pop(0.5, OptionType.CALL)
        assert result is not None
        assert 0.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_pop_put_valid(self) -> None:
        """Valid d2 for put produces result in [0, 1]."""
        result = compute_pop(0.5, OptionType.PUT)
        assert result is not None
        assert 0.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_pop_nan_d2(self) -> None:
        """NaN d2 returns None."""
        assert compute_pop(float("nan"), OptionType.CALL) is None

    @pytest.mark.audit_stability
    def test_pop_inf_d2(self) -> None:
        """Inf d2 returns None."""
        assert compute_pop(float("inf"), OptionType.CALL) is None


class TestComputeOptimalDTEStability:
    """Stability tests for compute_optimal_dte."""

    @pytest.mark.audit_stability
    def test_optimal_dte_valid(self) -> None:
        """Valid inputs produce finite result."""
        result = compute_optimal_dte(-0.05, 2.0)
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_optimal_dte_none_ev(self) -> None:
        """None expected value returns None."""
        assert compute_optimal_dte(-0.05, None) is None

    @pytest.mark.audit_stability
    def test_optimal_dte_zero_theta(self) -> None:
        """Zero theta returns None."""
        assert compute_optimal_dte(0.0, 2.0) is None

    @pytest.mark.audit_stability
    def test_optimal_dte_nan(self) -> None:
        """NaN theta returns None."""
        assert compute_optimal_dte(float("nan"), 2.0) is None


class TestComputeSpreadQualityStability:
    """Stability tests for compute_spread_quality."""

    @pytest.mark.audit_stability
    def test_spread_quality_valid(self) -> None:
        """Valid chain produces finite non-negative result."""
        chain = pd.DataFrame(
            {
                "bid": [5.0, 4.0, 3.0],
                "ask": [5.50, 4.50, 3.50],
                "openInterest": [1000, 500, 200],
            }
        )
        result = compute_spread_quality(chain)
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_spread_quality_empty(self) -> None:
        """Empty chain returns None."""
        chain = pd.DataFrame({"bid": [], "ask": [], "openInterest": []})
        assert compute_spread_quality(chain) is None

    @pytest.mark.audit_stability
    def test_spread_quality_zero_oi(self) -> None:
        """All-zero OI returns None."""
        chain = pd.DataFrame(
            {
                "bid": [5.0],
                "ask": [5.50],
                "openInterest": [0],
            }
        )
        assert compute_spread_quality(chain) is None

    @pytest.mark.audit_stability
    def test_spread_quality_missing_columns(self) -> None:
        """Missing columns returns None."""
        chain = pd.DataFrame({"bid": [5.0], "ask": [5.50]})
        assert compute_spread_quality(chain) is None


class TestComputeMaxLossRatioStability:
    """Stability tests for compute_max_loss_ratio."""

    @pytest.mark.audit_stability
    def test_max_loss_ratio_valid(self) -> None:
        """Valid inputs produce finite positive result."""
        result = compute_max_loss_ratio(500.0, 10000.0)
        assert result is not None
        assert math.isfinite(result)
        assert result == pytest.approx(0.05, abs=1e-10)

    @pytest.mark.audit_stability
    def test_max_loss_ratio_zero_cost(self) -> None:
        """Zero cost returns None."""
        assert compute_max_loss_ratio(0.0, 10000.0) is None

    @pytest.mark.audit_stability
    def test_max_loss_ratio_zero_budget(self) -> None:
        """Zero budget returns None."""
        assert compute_max_loss_ratio(500.0, 0.0) is None

    @pytest.mark.audit_stability
    def test_max_loss_ratio_nan(self) -> None:
        """NaN inputs return None."""
        assert compute_max_loss_ratio(float("nan"), 10000.0) is None

    @pytest.mark.audit_stability
    def test_max_loss_ratio_negative(self) -> None:
        """Negative inputs return None."""
        assert compute_max_loss_ratio(-100.0, 10000.0) is None


# ===========================================================================
# Flow Analytics Stability (5 functions)
# ===========================================================================


class TestComputeGEXStability:
    """Stability tests for compute_gex."""

    @pytest.mark.audit_stability
    def test_gex_valid(self) -> None:
        """Valid chain data produces finite result."""
        calls = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "openInterest": [1000, 2000, 1500],
                "gamma": [0.05, 0.08, 0.04],
            }
        )
        puts = pd.DataFrame(
            {
                "strike": [95.0, 100.0, 105.0],
                "openInterest": [800, 1500, 1200],
                "gamma": [0.04, 0.07, 0.03],
            }
        )
        result = compute_gex(calls, puts, 100.0)
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_gex_empty_chains(self) -> None:
        """Empty chains return None."""
        empty = pd.DataFrame({"openInterest": [], "gamma": []})
        assert compute_gex(empty, empty, 100.0) is None

    @pytest.mark.audit_stability
    def test_gex_zero_spot(self) -> None:
        """Zero spot returns None."""
        calls = pd.DataFrame({"openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"openInterest": [100], "gamma": [0.05]})
        assert compute_gex(calls, puts, 0.0) is None

    @pytest.mark.audit_stability
    def test_gex_nan_spot(self) -> None:
        """NaN spot returns None."""
        calls = pd.DataFrame({"openInterest": [100], "gamma": [0.05]})
        puts = pd.DataFrame({"openInterest": [100], "gamma": [0.05]})
        assert compute_gex(calls, puts, float("nan")) is None


class TestComputeOIConcentrationStability:
    """Stability tests for compute_oi_concentration."""

    @pytest.mark.audit_stability
    def test_oi_concentration_valid(self) -> None:
        """Valid chain produces result in [0, 1]."""
        chain = pd.DataFrame({"openInterest": [1000, 500, 200]})
        result = compute_oi_concentration(chain)
        assert result is not None
        assert 0.0 <= result <= 1.0

    @pytest.mark.audit_stability
    def test_oi_concentration_empty(self) -> None:
        """Empty chain returns None."""
        assert compute_oi_concentration(pd.DataFrame({"openInterest": []})) is None

    @pytest.mark.audit_stability
    def test_oi_concentration_zero_oi(self) -> None:
        """All-zero OI returns None."""
        assert compute_oi_concentration(pd.DataFrame({"openInterest": [0, 0]})) is None


class TestComputeUnusualActivityStability:
    """Stability tests for compute_unusual_activity."""

    @pytest.mark.audit_stability
    def test_unusual_activity_valid(self) -> None:
        """Chain with unusual strikes produces finite non-negative result."""
        chain = pd.DataFrame(
            {
                "volume": [5000, 100, 200],
                "openInterest": [1000, 500, 200],
                "bid": [5.0, 3.0, 2.0],
                "ask": [5.50, 3.50, 2.50],
            }
        )
        result = compute_unusual_activity(chain)
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_unusual_activity_empty(self) -> None:
        """Empty chain returns None."""
        chain = pd.DataFrame({"volume": [], "openInterest": [], "bid": [], "ask": []})
        assert compute_unusual_activity(chain) is None

    @pytest.mark.audit_stability
    def test_unusual_activity_no_unusual(self) -> None:
        """Chain with no unusual strikes returns 0.0."""
        chain = pd.DataFrame(
            {
                "volume": [100, 100],
                "openInterest": [1000, 1000],
                "bid": [5.0, 3.0],
                "ask": [5.50, 3.50],
            }
        )
        result = compute_unusual_activity(chain)
        assert result == 0.0


class TestComputeMaxPainMagnetStability:
    """Stability tests for compute_max_pain_magnet."""

    @pytest.mark.audit_stability
    def test_max_pain_magnet_at_pain(self) -> None:
        """Spot at max pain produces 1.0."""
        result = compute_max_pain_magnet(100.0, 100.0)
        assert result is not None
        assert result == pytest.approx(1.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_max_pain_magnet_away(self) -> None:
        """Spot 10% away from max pain produces < 1.0."""
        result = compute_max_pain_magnet(100.0, 110.0)
        assert result is not None
        assert result < 1.0

    @pytest.mark.audit_stability
    def test_max_pain_magnet_none(self) -> None:
        """None max_pain returns None."""
        assert compute_max_pain_magnet(100.0, None) is None

    @pytest.mark.audit_stability
    def test_max_pain_magnet_zero_spot(self) -> None:
        """Zero spot returns None."""
        assert compute_max_pain_magnet(0.0, 100.0) is None

    @pytest.mark.audit_stability
    def test_max_pain_magnet_nan(self) -> None:
        """NaN spot returns None."""
        assert compute_max_pain_magnet(float("nan"), 100.0) is None


class TestComputeDollarVolumeTrendStability:
    """Stability tests for compute_dollar_volume_trend."""

    @pytest.mark.audit_stability
    def test_dollar_volume_trend_valid(self) -> None:
        """Valid inputs produce finite result."""
        df = _make_ohlcv_df(30)
        result = compute_dollar_volume_trend(df["close"], df["volume"])
        assert result is not None
        assert math.isfinite(result)

    @pytest.mark.audit_stability
    def test_dollar_volume_trend_insufficient(self) -> None:
        """Short series returns None."""
        result = compute_dollar_volume_trend(pd.Series([100.0] * 5), pd.Series([1000.0] * 5))
        assert result is None

    @pytest.mark.audit_stability
    def test_dollar_volume_trend_flat(self) -> None:
        """Flat dollar volume produces near-zero slope."""
        close = pd.Series([100.0] * 25)
        volume = pd.Series([1000.0] * 25)
        result = compute_dollar_volume_trend(close, volume)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.audit_stability
    def test_dollar_volume_trend_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            compute_dollar_volume_trend(pd.Series([100.0] * 20), pd.Series([1000.0] * 21))


# ===========================================================================
# HV Estimators Stability (3 functions)
# ===========================================================================


class TestComputeHVParkinsonStability:
    """Stability tests for compute_hv_parkinson."""

    @pytest.mark.audit_stability
    def test_hv_parkinson_valid(self) -> None:
        """Valid OHLC data produces finite non-negative result."""
        df = _make_ohlcv_df(30)
        result = compute_hv_parkinson(df["high"], df["low"])
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_hv_parkinson_insufficient(self) -> None:
        """Short series returns None."""
        high = pd.Series([101.0] * 10)
        low = pd.Series([99.0] * 10)
        assert compute_hv_parkinson(high, low) is None

    @pytest.mark.audit_stability
    def test_hv_parkinson_flat(self) -> None:
        """Flat data (high == low) produces zero vol."""
        n = 25
        prices = pd.Series([100.0] * n)
        result = compute_hv_parkinson(prices, prices)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    @pytest.mark.audit_stability
    def test_hv_parkinson_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            compute_hv_parkinson(pd.Series([101.0] * 25), pd.Series([99.0] * 26))


class TestComputeHVRogersSatchellStability:
    """Stability tests for compute_hv_rogers_satchell."""

    @pytest.mark.audit_stability
    def test_hv_rogers_satchell_valid(self) -> None:
        """Valid OHLC data produces finite non-negative result."""
        df = _make_ohlcv_df(30)
        result = compute_hv_rogers_satchell(df["open"], df["high"], df["low"], df["close"])
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_hv_rogers_satchell_insufficient(self) -> None:
        """Short series returns None."""
        s = pd.Series([100.0] * 10)
        assert compute_hv_rogers_satchell(s, s, s, s) is None

    @pytest.mark.audit_stability
    def test_hv_rogers_satchell_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        s = pd.Series([100.0] * 25)
        with pytest.raises(ValueError):
            compute_hv_rogers_satchell(s, s, s, pd.Series([100.0] * 26))


class TestComputeHVYangZhangStability:
    """Stability tests for compute_hv_yang_zhang."""

    @pytest.mark.audit_stability
    def test_hv_yang_zhang_valid(self) -> None:
        """Valid OHLC data produces finite non-negative result."""
        df = _make_ohlcv_df(30)
        result = compute_hv_yang_zhang(df["open"], df["high"], df["low"], df["close"])
        assert result is not None
        assert math.isfinite(result)
        assert result >= 0.0

    @pytest.mark.audit_stability
    def test_hv_yang_zhang_insufficient(self) -> None:
        """Short series returns None."""
        s = pd.Series([100.0] * 10)
        assert compute_hv_yang_zhang(s, s, s, s) is None

    @pytest.mark.audit_stability
    def test_hv_yang_zhang_mismatched(self) -> None:
        """Mismatched lengths raise ValueError."""
        s = pd.Series([100.0] * 25)
        with pytest.raises(ValueError):
            compute_hv_yang_zhang(s, s, s, pd.Series([100.0] * 26))


# ===========================================================================
# Vol Surface Stability (2 functions)
# ===========================================================================


class TestComputeVolSurfaceStability:
    """Stability tests for compute_vol_surface."""

    @pytest.mark.audit_stability
    def test_vol_surface_valid_tier2(self) -> None:
        """Valid data with 3+ contracts produces a VolSurfaceResult."""
        strikes = np.array([95.0, 100.0, 105.0, 110.0])
        ivs = np.array([0.35, 0.30, 0.28, 0.32])
        dtes = np.array([30.0, 30.0, 30.0, 30.0])
        option_types = np.array([-1.0, 1.0, 1.0, -1.0])
        result = compute_vol_surface(strikes, ivs, dtes, option_types, 100.0)
        assert isinstance(result, VolSurfaceResult)

    @pytest.mark.audit_stability
    def test_vol_surface_insufficient(self) -> None:
        """Fewer than 3 contracts returns all-None result."""
        strikes = np.array([100.0, 105.0])
        ivs = np.array([0.30, 0.28])
        dtes = np.array([30.0, 30.0])
        option_types = np.array([1.0, 1.0])
        result = compute_vol_surface(strikes, ivs, dtes, option_types, 100.0)
        assert result.skew_25d is None
        assert result.smile_curvature is None

    @pytest.mark.audit_stability
    def test_vol_surface_zero_spot(self) -> None:
        """Zero spot returns all-None result."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.30, 0.28])
        dtes = np.array([30.0, 30.0, 30.0])
        option_types = np.array([-1.0, 1.0, 1.0])
        result = compute_vol_surface(strikes, ivs, dtes, option_types, 0.0)
        assert result.skew_25d is None

    @pytest.mark.audit_stability
    def test_vol_surface_nan_spot(self) -> None:
        """NaN spot returns all-None result."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([0.35, 0.30, 0.28])
        dtes = np.array([30.0, 30.0, 30.0])
        option_types = np.array([-1.0, 1.0, 1.0])
        result = compute_vol_surface(strikes, ivs, dtes, option_types, float("nan"))
        assert result.skew_25d is None

    @pytest.mark.audit_stability
    def test_vol_surface_nan_ivs(self) -> None:
        """NaN IVs produce graceful result (no crash)."""
        strikes = np.array([95.0, 100.0, 105.0])
        ivs = np.array([float("nan"), 0.30, 0.28])
        dtes = np.array([30.0, 30.0, 30.0])
        option_types = np.array([-1.0, 1.0, 1.0])
        result = compute_vol_surface(strikes, ivs, dtes, option_types, 100.0)
        assert isinstance(result, VolSurfaceResult)


class TestComputeSurfaceIndicatorsStability:
    """Stability tests for compute_surface_indicators."""

    @pytest.mark.audit_stability
    def test_surface_indicators_standalone_fallback(self) -> None:
        """Standalone fallback result returns empty indicators."""
        result = VolSurfaceResult(
            skew_25d=0.05,
            smile_curvature=0.10,
            prob_above_current=0.55,
            atm_iv_30d=0.30,
            atm_iv_60d=0.32,
            fitted_ivs=None,
            residuals=None,
            z_scores=None,
            r_squared=None,
            fitted_strikes=None,
            fitted_dtes=None,
            is_1d_fallback=False,
            is_standalone_fallback=True,
        )
        indicators = compute_surface_indicators(
            result, 100.0, 30.0, np.array([100.0]), np.array([30.0])
        )
        assert indicators.iv_surface_residual is None

    @pytest.mark.audit_stability
    def test_surface_indicators_with_z_scores(self) -> None:
        """Result with z_scores returns matching residual."""
        z_scores = np.array([1.5, -0.5, 0.3])
        strikes = np.array([95.0, 100.0, 105.0])
        dtes = np.array([30.0, 30.0, 30.0])
        result = VolSurfaceResult(
            skew_25d=0.05,
            smile_curvature=0.10,
            prob_above_current=0.55,
            atm_iv_30d=0.30,
            atm_iv_60d=0.32,
            fitted_ivs=np.array([0.31, 0.29, 0.28]),
            residuals=np.array([0.02, -0.01, 0.005]),
            z_scores=z_scores,
            r_squared=0.95,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
            is_1d_fallback=False,
            is_standalone_fallback=False,
        )
        indicators = compute_surface_indicators(result, 100.0, 30.0, strikes, dtes)
        assert indicators.iv_surface_residual is not None
        assert indicators.iv_surface_residual == pytest.approx(-0.5, abs=1e-10)
        assert indicators.surface_fit_r2 == pytest.approx(0.95, abs=1e-10)

    @pytest.mark.audit_stability
    def test_surface_indicators_no_match(self) -> None:
        """Contract not in surface arrays returns None residual."""
        z_scores = np.array([1.5])
        strikes = np.array([95.0])
        dtes = np.array([30.0])
        result = VolSurfaceResult(
            skew_25d=0.05,
            smile_curvature=0.10,
            prob_above_current=0.55,
            atm_iv_30d=0.30,
            atm_iv_60d=0.32,
            fitted_ivs=np.array([0.31]),
            residuals=np.array([0.02]),
            z_scores=z_scores,
            r_squared=0.95,
            fitted_strikes=strikes,
            fitted_dtes=dtes,
            is_1d_fallback=False,
            is_standalone_fallback=False,
        )
        indicators = compute_surface_indicators(result, 200.0, 60.0, strikes, dtes)
        assert indicators.iv_surface_residual is None
        assert indicators.surface_fit_r2 == pytest.approx(0.95, abs=1e-10)


# ===========================================================================
# NaN Injection Across All Indicators
# ===========================================================================


class TestIndicatorNaNInjection:
    """Inject NaN into DataFrames at various positions for all indicators."""

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last", "multiple"],
        ids=["nan_first", "nan_middle", "nan_last", "nan_multiple"],
    )
    def test_rsi_nan_injection(self, nan_position: str) -> None:
        """NaN in close at various positions does not crash RSI."""
        close = _make_close_series(50)
        close = _inject_nan(close, nan_position)
        result = rsi(close)
        assert len(result) == len(close)

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last"],
        ids=["nan_first", "nan_middle", "nan_last"],
    )
    def test_adx_nan_injection(self, nan_position: str) -> None:
        """NaN in OHLC at various positions does not crash ADX."""
        df = _make_ohlcv_df(50)
        df.loc[df.index[_nan_index(len(df), nan_position)], "close"] = float("nan")
        result = adx(df["high"], df["low"], df["close"])
        assert len(result) == len(df)

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last"],
        ids=["nan_first", "nan_middle", "nan_last"],
    )
    def test_bb_width_nan_injection(self, nan_position: str) -> None:
        """NaN in close at various positions does not crash BB width."""
        close = _make_close_series(50)
        close = _inject_nan(close, nan_position)
        result = bb_width(close, period=20)
        assert len(result) == len(close)

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last"],
        ids=["nan_first", "nan_middle", "nan_last"],
    )
    def test_macd_nan_injection(self, nan_position: str) -> None:
        """NaN in close at various positions does not crash MACD."""
        close = _make_close_series(50)
        close = _inject_nan(close, nan_position)
        # MACD may raise InsufficientDataError for all-NaN, which is acceptable
        try:
            result = macd(close)
            assert len(result) == len(close)
        except InsufficientDataError:
            pass

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last"],
        ids=["nan_first", "nan_middle", "nan_last"],
    )
    def test_obv_trend_nan_injection(self, nan_position: str) -> None:
        """NaN in close/volume at various positions does not crash OBV trend."""
        df = _make_ohlcv_df(50)
        df.loc[df.index[_nan_index(len(df), nan_position)], "close"] = float("nan")
        result = obv_trend(df["close"], df["volume"])
        assert len(result) == len(df)

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "nan_position",
        ["first", "middle", "last"],
        ids=["nan_first", "nan_middle", "nan_last"],
    )
    def test_roc_nan_injection(self, nan_position: str) -> None:
        """NaN in close at various positions does not crash ROC."""
        close = _make_close_series(50)
        close = _inject_nan(close, nan_position)
        result = roc(close)
        assert len(result) == len(close)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nan_index(length: int, position: str) -> int:
    """Return the index to inject NaN at."""
    if position == "first":
        return 0
    elif position == "last":
        return length - 1
    else:
        return length // 2


def _inject_nan(series: pd.Series, position: str) -> pd.Series:
    """Inject NaN into a series at the specified position."""
    s = series.copy()
    if position == "multiple":
        indices = [0, len(s) // 4, len(s) // 2, 3 * len(s) // 4]
        for idx in indices:
            s.iloc[idx] = float("nan")
    else:
        s.iloc[_nan_index(len(s), position)] = float("nan")
    return s
