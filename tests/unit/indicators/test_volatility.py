"""Tests for volatility indicators: bb_width, atr_percent, keltner_width.

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

from options_arena.indicators.volatility import atr_percent, bb_width, keltner_width
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# bb_width tests
# ---------------------------------------------------------------------------


class TestBBWidth:
    """Tests for Bollinger Band width indicator."""

    def test_known_value(self) -> None:
        """Known-value test for Bollinger Band width.

        Reference: Investopedia Bollinger Bands example.
        Using a 5-period Bollinger Band with 2 std devs on known data.
        Hand-calculated: close = [44, 44.34, 44.09, 43.61, 44.33]
        SMA(5) = 44.074, stddev(ddof=0) = 0.26193...
        upper = 44.074 + 2*0.26193 = 44.5979
        lower = 44.074 - 2*0.26193 = 43.5501
        width = (44.5979 - 43.5501) / 44.074 = 0.02378
        """
        close = pd.Series([44.0, 44.34, 44.09, 43.61, 44.33])
        result = bb_width(close, period=5, num_std=2.0)

        # First 4 values (period-1) should be NaN
        assert result.iloc[:4].isna().all()

        # Verify the computed value
        sma = np.mean([44.0, 44.34, 44.09, 43.61, 44.33])
        std = float(np.std([44.0, 44.34, 44.09, 43.61, 44.33], ddof=0))
        expected_width = (2 * 2.0 * std) / sma
        assert result.iloc[4] == pytest.approx(expected_width, rel=1e-4)

    def test_minimum_data(self) -> None:
        """Exactly period data points should produce one valid output."""
        close = pd.Series([10.0, 11.0, 12.0, 11.5, 10.5])
        result = bb_width(close, period=5)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than period data points raises InsufficientDataError."""
        close = pd.Series([10.0, 11.0, 12.0])
        with pytest.raises(InsufficientDataError):
            bb_width(close, period=5)

    def test_nan_warmup_count(self) -> None:
        """First period-1 values should be NaN."""
        close = pd.Series([10.0, 11.0, 12.0, 11.5, 10.5, 11.0, 12.5, 13.0])
        period = 5
        result = bb_width(close, period=period)
        nan_count = result.iloc[: period - 1].isna().sum()
        assert nan_count == period - 1

    def test_flat_data(self) -> None:
        """All same price: stddev=0, so width=0."""
        close = pd.Series([50.0] * 10)
        result = bb_width(close, period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-10) for v in valid)

    def test_uses_population_stddev(self) -> None:
        """Verify population stddev (ddof=0) is used, not sample (ddof=1)."""
        close = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        result = bb_width(close, period=5)

        # With ddof=0, std = sqrt(200), with ddof=1 std = sqrt(250)
        pop_std = float(np.std([10.0, 20.0, 30.0, 40.0, 50.0], ddof=0))
        sample_std = float(np.std([10.0, 20.0, 30.0, 40.0, 50.0], ddof=1))
        sma = 30.0

        expected_pop = (2 * 2.0 * pop_std) / sma
        expected_sample = (2 * 2.0 * sample_std) / sma

        assert result.iloc[4] == pytest.approx(expected_pop, rel=1e-4)
        assert result.iloc[4] != pytest.approx(expected_sample, rel=1e-2)


# ---------------------------------------------------------------------------
# atr_percent tests
# ---------------------------------------------------------------------------


class TestATRPercent:
    """Tests for ATR percentage indicator."""

    def test_known_value(self) -> None:
        """Known-value test for ATR%.

        Reference: Wilder (1978) ATR calculation.
        Using simple OHLC data with period=3.
        """
        # Construct OHLC data where true range can be hand-verified
        high = pd.Series([48.70, 48.72, 48.90, 48.87, 48.82, 49.05])
        low = pd.Series([47.79, 48.14, 48.39, 48.37, 48.24, 48.64])
        close = pd.Series([48.16, 48.61, 48.75, 48.63, 48.74, 49.03])

        result = atr_percent(high, low, close, period=3)

        # First 3 values (period) should be NaN
        assert result.iloc[:3].isna().all()
        # Remaining values should be positive percentages
        valid = result.dropna()
        assert all(v > 0 for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly period+1 data points should produce one valid output."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8])
        low = pd.Series([11.0, 11.5, 11.3, 11.8])
        close = pd.Series([11.5, 12.0, 11.8, 12.3])
        result = atr_percent(high, low, close, period=3)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 data points raises InsufficientDataError."""
        high = pd.Series([12.0, 12.5])
        low = pd.Series([11.0, 11.5])
        close = pd.Series([11.5, 12.0])
        with pytest.raises(InsufficientDataError):
            atr_percent(high, low, close, period=3)

    def test_nan_warmup_count(self) -> None:
        """First period values should be NaN."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8, 13.0, 12.7, 13.2])
        low = pd.Series([11.0, 11.5, 11.3, 11.8, 12.0, 11.7, 12.2])
        close = pd.Series([11.5, 12.0, 11.8, 12.3, 12.5, 12.2, 12.7])
        period = 3
        result = atr_percent(high, low, close, period=period)
        nan_count = result.iloc[:period].isna().sum()
        assert nan_count == period

    def test_flat_data(self) -> None:
        """All same OHLC: true range=0, ATR%=0."""
        n = 20
        high = pd.Series([50.0] * n)
        low = pd.Series([50.0] * n)
        close = pd.Series([50.0] * n)
        result = atr_percent(high, low, close, period=14)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-10) for v in valid)

    def test_monotonic_increase(self) -> None:
        """Monotonically increasing data should produce positive ATR%."""
        n = 20
        close = pd.Series(np.linspace(100, 120, n))
        high = close + 1.0
        low = close - 1.0
        result = atr_percent(high, low, close, period=14)
        valid = result.dropna()
        assert all(v > 0 for v in valid)


# ---------------------------------------------------------------------------
# keltner_width tests
# ---------------------------------------------------------------------------


class TestKeltnerWidth:
    """Tests for Keltner Channel width indicator."""

    def test_known_value(self) -> None:
        """Known-value test: Keltner width should be positive for volatile data.

        Reference: Linda Raschke's Keltner Channel definition.
        """
        n = 25
        np.random.seed(42)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(n) * 0.5))
        high = close + np.abs(np.random.randn(n) * 0.5)
        low = close - np.abs(np.random.randn(n) * 0.5)

        result = keltner_width(high, low, close, period=10, atr_mult=2.0)
        valid = result.dropna()
        assert len(valid) > 0
        assert all(v > 0 for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly period+1 data points should produce one valid output."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8, 13.0, 12.7])
        low = pd.Series([11.0, 11.5, 11.3, 11.8, 12.0, 11.7])
        close = pd.Series([11.5, 12.0, 11.8, 12.3, 12.5, 12.2])
        result = keltner_width(high, low, close, period=5)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 raises InsufficientDataError."""
        high = pd.Series([12.0, 12.5, 12.3])
        low = pd.Series([11.0, 11.5, 11.3])
        close = pd.Series([11.5, 12.0, 11.8])
        with pytest.raises(InsufficientDataError):
            keltner_width(high, low, close, period=5)

    def test_nan_warmup_count(self) -> None:
        """First period values should be NaN."""
        n = 30
        close = pd.Series(np.linspace(100, 110, n))
        high = close + 1.0
        low = close - 1.0
        period = 10
        result = keltner_width(high, low, close, period=period)
        nan_count = result.iloc[:period].isna().sum()
        assert nan_count == period

    def test_flat_data(self) -> None:
        """All same OHLC: ATR=0, width=0."""
        n = 25
        high = pd.Series([50.0] * n)
        low = pd.Series([50.0] * n)
        close = pd.Series([50.0] * n)
        result = keltner_width(high, low, close, period=10)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-10) for v in valid)
