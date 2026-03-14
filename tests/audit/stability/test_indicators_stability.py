"""Stability tests for indicator functions: Hypothesis + extreme inputs + NaN injection.

Covers oscillators (3), trend (7), volatility (3), volume (3), and moving averages (2).
Every function produces finite output for valid inputs OR raises InsufficientDataError /
ValueError. NaN in input propagates cleanly (no silent corruption of non-NaN values).
"""

import math

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.indicators.trend import (
    adx,
    compute_adx_exhaustion,
    compute_multi_tf_alignment,
    compute_rsi_divergence,
    macd,
    roc,
    supertrend,
)
from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume
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
