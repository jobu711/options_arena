"""Tests for moving average indicators: sma_alignment, vwap_deviation.

Every indicator is tested with all five required test types:
1. Known-value test (with source citation)
2. Minimum data test
3. Insufficient data test
4. NaN warmup test
5. Edge cases (flat, monotonic, etc.)
"""

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# sma_alignment tests
# ---------------------------------------------------------------------------


class TestSMAAlignment:
    """Tests for SMA alignment indicator."""

    def test_known_value_bullish(self) -> None:
        """Known-value test: monotonically increasing prices give positive alignment.

        Reference: Standard SMA alignment interpretation.
        When price is rising, short SMA > long SMA, alignment is positive (bullish).
        """
        n = 250
        close = pd.Series(np.linspace(100, 200, n))
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert len(valid) > 0
        # Short SMA > Long SMA for uptrend => positive alignment
        assert all(v > 0 for v in valid)

    def test_known_value_bearish(self) -> None:
        """Monotonically decreasing prices give negative alignment."""
        n = 250
        close = pd.Series(np.linspace(200, 100, n))
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert len(valid) > 0
        # Short SMA < Long SMA for downtrend => negative alignment
        assert all(v < 0 for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly long data points should produce one valid output."""
        close = pd.Series(np.linspace(100, 200, 200))
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than long data points raises InsufficientDataError."""
        close = pd.Series(np.linspace(100, 150, 100))
        with pytest.raises(InsufficientDataError):
            sma_alignment(close, short=20, medium=50, long=200)

    def test_nan_warmup_count(self) -> None:
        """First long-1 values should be NaN."""
        n = 250
        close = pd.Series(np.linspace(100, 200, n))
        long_period = 200
        result = sma_alignment(close, short=20, medium=50, long=long_period)
        nan_count = result.iloc[: long_period - 1].isna().sum()
        assert nan_count == long_period - 1

    def test_flat_data(self) -> None:
        """All same price: all SMAs equal, alignment=0."""
        close = pd.Series([100.0] * 250)
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)


# ---------------------------------------------------------------------------
# vwap_deviation tests
# ---------------------------------------------------------------------------


class TestVWAPDeviation:
    """Tests for VWAP deviation indicator."""

    def test_known_value(self) -> None:
        """Known-value test: hand-calculated VWAP deviation.

        Reference: Standard cumulative VWAP calculation.
        Data: close=[10, 20], volume=[100, 100]
        VWAP at index 0: 10*100/100 = 10, dev = 0%
        VWAP at index 1: (10*100 + 20*100) / (100+100) = 15, dev = (20-15)/15*100 = 33.33%
        """
        close = pd.Series([10.0, 20.0])
        volume = pd.Series([100.0, 100.0])
        result = vwap_deviation(close, volume)

        assert result.iloc[0] == pytest.approx(0.0, abs=1e-4)
        assert result.iloc[1] == pytest.approx(33.3333, rel=1e-4)

    def test_constant_price(self) -> None:
        """Constant price: VWAP = close at all times, deviation = 0."""
        close = pd.Series([50.0] * 20)
        volume = pd.Series([1000.0] * 20)
        result = vwap_deviation(close, volume)
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in result)

    def test_minimum_data(self) -> None:
        """Single data point gives deviation = 0."""
        close = pd.Series([100.0])
        volume = pd.Series([1000.0])
        result = vwap_deviation(close, volume)
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-6)

    def test_insufficient_data(self) -> None:
        """Empty series raises InsufficientDataError."""
        close = pd.Series([], dtype=float)
        volume = pd.Series([], dtype=float)
        with pytest.raises(InsufficientDataError):
            vwap_deviation(close, volume)

    def test_no_nan_warmup(self) -> None:
        """VWAP deviation has no warmup: all values computed from start."""
        close = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        volume = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0])
        result = vwap_deviation(close, volume)
        assert result.isna().sum() == 0

    def test_rising_prices_positive_deviation(self) -> None:
        """Rising prices: close > VWAP, deviation positive."""
        close = pd.Series(np.arange(10.0, 20.0))
        volume = pd.Series([1000.0] * 10)
        result = vwap_deviation(close, volume)
        # After first bar, price > VWAP (since VWAP is average of all prior prices)
        assert result.iloc[-1] > 0

    def test_falling_prices_negative_deviation(self) -> None:
        """Falling prices: close < VWAP, deviation negative."""
        close = pd.Series(np.arange(20.0, 10.0, -1.0))
        volume = pd.Series([1000.0] * 10)
        result = vwap_deviation(close, volume)
        # After first bar, price < VWAP
        assert result.iloc[-1] < 0
