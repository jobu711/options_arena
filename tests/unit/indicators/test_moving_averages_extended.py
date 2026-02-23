"""Extended moving average tests: full 5-test pattern for sma_alignment and vwap_deviation.

The original test file had only 13 tests. These add the complete set of
edge cases and minimum-data tests per the CLAUDE.md indicator test pattern.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.moving_averages import sma_alignment, vwap_deviation
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# sma_alignment — extended tests
# ---------------------------------------------------------------------------


class TestSMAAlignmentExtended:
    """Additional tests for sma_alignment following the 5-test pattern."""

    def test_known_value_perfectly_aligned_uptrend(self) -> None:
        """Monotonically increasing prices -> positive alignment.

        When short SMA > medium SMA > long SMA, alignment should be positive.
        """
        # Ascending prices: short SMA > long SMA
        close = pd.Series(np.arange(210, dtype=float) + 100)
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert all(v > 0 for v in valid)

    def test_known_value_downtrend(self) -> None:
        """Monotonically decreasing prices -> negative alignment."""
        close = pd.Series(np.arange(210, dtype=float)[::-1] + 100)
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert all(v < 0 for v in valid)

    def test_minimum_data_exactly_long_period(self) -> None:
        """Exactly 200 data points: one valid output."""
        close = pd.Series(np.arange(200, dtype=float) + 100)
        result = sma_alignment(close, short=20, medium=50, long=200)
        # Last value should be valid
        assert not np.isnan(result.iloc[-1])

    def test_insufficient_data(self) -> None:
        close = pd.Series([100.0] * 199)
        with pytest.raises(InsufficientDataError):
            sma_alignment(close, short=20, medium=50, long=200)

    def test_nan_warmup_count(self) -> None:
        """First long-1 values are NaN."""
        close = pd.Series(np.arange(250, dtype=float) + 100)
        result = sma_alignment(close, short=20, medium=50, long=200)
        nan_count = result.iloc[:199].isna().sum()
        assert nan_count == 199

    def test_flat_data_zero_alignment(self) -> None:
        """All-same prices -> alignment is 0 (all SMAs equal)."""
        close = pd.Series([100.0] * 250)
        result = sma_alignment(close, short=20, medium=50, long=200)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_single_spike(self) -> None:
        """Flat with a spike — alignment should react briefly then settle."""
        close = pd.Series([100.0] * 250)
        close.iloc[240] = 200.0  # spike
        result = sma_alignment(close, short=20, medium=50, long=200)
        # Post-spike alignment should differ from zero
        assert result.iloc[240] != 0.0


# ---------------------------------------------------------------------------
# vwap_deviation — extended tests
# ---------------------------------------------------------------------------


class TestVWAPDeviationExtended:
    """Additional tests for vwap_deviation following the 5-test pattern."""

    def test_known_value_constant_price(self) -> None:
        """Constant price -> deviation is 0 everywhere."""
        close = pd.Series([100.0] * 50)
        volume = pd.Series([1_000_000] * 50, dtype=float)
        result = vwap_deviation(close, volume)
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in result)

    def test_minimum_data_single_point(self) -> None:
        """Single data point is valid."""
        close = pd.Series([150.0])
        volume = pd.Series([500_000], dtype=float)
        result = vwap_deviation(close, volume)
        assert len(result) == 1
        # VWAP = close for single point -> deviation = 0
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-6)

    def test_insufficient_data_empty(self) -> None:
        close = pd.Series([], dtype=float)
        with pytest.raises(InsufficientDataError):
            vwap_deviation(close, pd.Series([], dtype=float))

    def test_ascending_price_positive_deviation(self) -> None:
        """Ascending prices -> current price above historical VWAP -> positive."""
        close = pd.Series(np.arange(50, dtype=float) + 100)
        volume = pd.Series([1_000_000] * 50, dtype=float)
        result = vwap_deviation(close, volume)
        # Last price is 149, VWAP is weighted toward lower early prices
        assert result.iloc[-1] > 0

    def test_descending_price_negative_deviation(self) -> None:
        """Descending prices -> current price below historical VWAP -> negative."""
        close = pd.Series(np.arange(50, dtype=float)[::-1] + 100)
        volume = pd.Series([1_000_000] * 50, dtype=float)
        result = vwap_deviation(close, volume)
        assert result.iloc[-1] < 0

    def test_zero_volume_produces_nan(self) -> None:
        """Zero cumulative volume -> VWAP undefined -> NaN."""
        close = pd.Series([100.0, 101.0, 102.0])
        volume = pd.Series([0.0, 0.0, 0.0])
        result = vwap_deviation(close, volume)
        assert all(np.isnan(v) for v in result)

    def test_no_nan_warmup(self) -> None:
        """vwap_deviation has NO warmup — all values computed from start."""
        close = pd.Series([100.0, 102.0, 104.0, 103.0, 105.0])
        volume = pd.Series([1_000_000.0] * 5)
        result = vwap_deviation(close, volume)
        # First value should be 0 (single-point VWAP = price)
        assert result.iloc[0] == pytest.approx(0.0, abs=1e-6)
        # No NaNs (assuming non-zero volume)
        assert result.isna().sum() == 0
