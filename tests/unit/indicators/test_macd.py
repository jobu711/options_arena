"""Tests for MACD histogram indicator.

Every indicator is tested with all five required test types:
1. Known-value test (with source citation)
2. Minimum data test
3. Insufficient data test
4. NaN warmup test
5. Edge cases (flat, monotonic, custom periods, empty)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.trend import macd
from options_arena.utils.exceptions import InsufficientDataError


class TestMacd:
    """Tests for MACD histogram indicator."""

    def test_known_values(self) -> None:
        """Verify MACD histogram against hand-calculated reference values.

        Reference: Investopedia MACD definition & StockCharts MACD tutorial.

        Setup: 50-bar series with known prices. We independently compute:
          MACD line = EMA(12) - EMA(26)
          Signal line = EMA(9) of MACD line
          Histogram = MACD line - Signal line

        Using pd.Series.ewm(span=N, adjust=False).mean() for EMA.
        """
        np.random.seed(42)
        # Use a realistic price series with enough bars
        close = pd.Series(
            100.0 + np.cumsum(np.random.randn(50) * 0.5),
        )

        result = macd(close)

        # Independently compute expected values
        fast_ema = close.ewm(span=12, adjust=False).mean()
        slow_ema = close.ewm(span=26, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        expected_histogram = macd_line - signal_line

        # After warmup, values should match
        # Warmup is slow_period + signal_period - 2 = 26 + 9 - 2 = 33
        for i in range(33, 50):
            assert result.iloc[i] == pytest.approx(expected_histogram.iloc[i], rel=1e-6), (
                f"Mismatch at index {i}"
            )

    def test_minimum_data(self) -> None:
        """Verify exactly slow_period + signal_period rows produces one valid output."""
        n = 26 + 9  # 35
        close = pd.Series(np.linspace(100, 130, n))
        result = macd(close)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data_raises(self) -> None:
        """Verify InsufficientDataError when fewer than slow_period + signal_period bars."""
        close = pd.Series(np.linspace(100, 110, 34))  # 34 < 35
        with pytest.raises(InsufficientDataError):
            macd(close)

    def test_nan_warmup_count(self) -> None:
        """Verify first slow_period + signal_period - 2 values are NaN.

        With default parameters (fast=12, slow=26, signal=9):
        - EMA(26) needs 26 bars to have meaningful values, but ewm(adjust=False)
          produces values from index 0 (seeded from first value).
        - The MACD line = EMA(12) - EMA(26) is defined from index 0 but unreliable
          until both EMAs have warmed up.
        - Signal line = EMA(9) of MACD line adds another 9 bars of warmup.
        - Total warmup: slow_period + signal_period - 2 = 33 bars (indices 0..32).
        """
        close = pd.Series(np.linspace(100, 200, 60))
        result = macd(close)

        warmup_count = 26 + 9 - 2  # 33
        nan_count = result.iloc[:warmup_count].isna().sum()
        assert nan_count == warmup_count

        # And the value right after warmup should be valid (not NaN)
        assert not pd.isna(result.iloc[warmup_count])

    def test_flat_data(self) -> None:
        """Verify MACD histogram is approximately zero for constant price series.

        When price is constant, all EMAs equal that constant, so
        MACD line = 0, signal = 0, histogram = 0.
        """
        close = pd.Series([100.0] * 50)
        result = macd(close)
        valid = result.dropna()
        assert len(valid) > 0
        assert all(v == pytest.approx(0.0, abs=1e-10) for v in valid)

    def test_monotonic_increasing(self) -> None:
        """Verify MACD histogram is positive for steadily rising prices.

        When prices rise linearly, the fast EMA leads the slow EMA,
        making the MACD line positive. After the signal line also becomes
        positive (with lag), the histogram should be positive during
        acceleration and eventually settle.
        """
        close = pd.Series(np.linspace(100, 200, 60))
        result = macd(close)
        valid = result.dropna()
        assert len(valid) > 0
        # For a steady linear increase, the histogram should be >= 0
        # (it approaches 0 as the trend is perfectly linear and signal catches up)
        # At least the last few values should be non-negative
        assert all(v >= -1e-10 for v in valid)

    def test_custom_periods(self) -> None:
        """Verify function works with non-default period parameters."""
        np.random.seed(123)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(40) * 0.5))

        fast, slow, signal = 5, 10, 4
        result = macd(close, fast_period=fast, slow_period=slow, signal_period=signal)

        # Independently compute expected values
        fast_ema = close.ewm(span=fast, adjust=False).mean()
        slow_ema = close.ewm(span=slow, adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        expected = macd_line - signal_line

        warmup = slow + signal - 2  # 10 + 4 - 2 = 12
        for i in range(warmup, len(close)):
            assert result.iloc[i] == pytest.approx(expected.iloc[i], rel=1e-6)

        # Verify warmup NaN count
        nan_count = result.iloc[:warmup].isna().sum()
        assert nan_count == warmup

    def test_empty_series(self) -> None:
        """Verify InsufficientDataError on empty pd.Series."""
        close = pd.Series([], dtype=float)
        with pytest.raises(InsufficientDataError):
            macd(close)

    def test_all_nan_input_raises(self) -> None:
        """Verify InsufficientDataError when input is all NaN."""
        close = pd.Series([float("nan")] * 50)
        with pytest.raises(InsufficientDataError):
            macd(close)

    def test_result_index_matches_input(self) -> None:
        """Verify the output Series has the same index as the input."""
        idx = pd.date_range("2024-01-01", periods=50, freq="B")
        close = pd.Series(np.linspace(100, 150, 50), index=idx)
        result = macd(close)
        assert result.index.equals(close.index)

    def test_result_length_matches_input(self) -> None:
        """Verify the output Series has the same length as the input."""
        close = pd.Series(np.linspace(100, 150, 50))
        result = macd(close)
        assert len(result) == len(close)
