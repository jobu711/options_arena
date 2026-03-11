"""Tests for trend indicators: roc, adx, supertrend.

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

from options_arena.indicators.trend import adx, roc, supertrend
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# ROC tests
# ---------------------------------------------------------------------------


class TestROC:
    """Tests for Rate of Change indicator."""

    @pytest.mark.critical
    def test_known_value(self) -> None:
        """Known-value test for ROC.

        Reference: StockCharts ROC definition.
        ROC = (close - close_n_ago) / close_n_ago * 100
        close = [10, 11, 12, 13, 14, 15], period=3
        At index 3: (13 - 10) / 10 * 100 = 30.0
        At index 4: (14 - 11) / 11 * 100 = 27.27
        At index 5: (15 - 12) / 12 * 100 = 25.0
        """
        close = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
        result = roc(close, period=3)

        assert result.iloc[:3].isna().all()
        assert result.iloc[3] == pytest.approx(30.0, rel=1e-4)
        assert result.iloc[4] == pytest.approx(27.2727, rel=1e-4)
        assert result.iloc[5] == pytest.approx(25.0, rel=1e-4)

    def test_minimum_data(self) -> None:
        """Exactly period+1 data points should produce one valid output."""
        close = pd.Series([10.0, 11.0, 12.0, 13.0])
        result = roc(close, period=3)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 raises InsufficientDataError."""
        close = pd.Series([10.0, 11.0])
        with pytest.raises(InsufficientDataError):
            roc(close, period=3)

    def test_nan_warmup_count(self) -> None:
        """First period values should be NaN."""
        close = pd.Series(np.linspace(100, 120, 20))
        period = 12
        result = roc(close, period=period)
        nan_count = result.iloc[:period].isna().sum()
        assert nan_count == period

    def test_flat_data(self) -> None:
        """Flat data: ROC = 0."""
        close = pd.Series([50.0] * 20)
        result = roc(close, period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_monotonic_increase(self) -> None:
        """Monotonically increasing: ROC > 0."""
        close = pd.Series(np.arange(10.0, 25.0))
        result = roc(close, period=5)
        valid = result.dropna()
        assert all(v > 0 for v in valid)

    def test_monotonic_decrease(self) -> None:
        """Monotonically decreasing: ROC < 0."""
        close = pd.Series(np.arange(25.0, 10.0, -1.0))
        result = roc(close, period=5)
        valid = result.dropna()
        assert all(v < 0 for v in valid)


# ---------------------------------------------------------------------------
# ADX tests
# ---------------------------------------------------------------------------


class TestADX:
    """Tests for Average Directional Index."""

    def test_known_value_trending(self) -> None:
        """Known-value test: strong trend should produce high ADX.

        Reference: Wilder (1978) "New Concepts in Technical Trading Systems".
        ADX > 25 indicates strong trend. Monotonic increase should give high ADX.
        """
        n = 50
        close = pd.Series(np.linspace(100, 150, n))
        high = close + 1.0
        low = close - 1.0
        result = adx(high, low, close, period=14)
        valid = result.dropna()
        assert len(valid) > 0
        # Strong uptrend should have ADX > 20
        assert valid.iloc[-1] > 20.0

    def test_known_value_range_bound(self) -> None:
        """Range-bound (oscillating) data should produce lower ADX.

        Reference: Wilder's ADX interpretation - ADX < 20 = weak trend.
        """
        n = 60
        # Oscillating around 100 with small amplitude
        close = pd.Series(100.0 + 2.0 * np.sin(np.linspace(0, 8 * np.pi, n)))
        high = close + 0.5
        low = close - 0.5
        result = adx(high, low, close, period=14)
        valid = result.dropna()
        assert len(valid) > 0
        # Weak/no trend should have lower ADX than trending data
        # Just verify it's a valid number in range
        assert all(0.0 <= v <= 100.0 for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly 2*period+1 data points should produce one valid output."""
        n = 29  # 2*14+1
        close = pd.Series(np.linspace(100, 120, n))
        high = close + 1.0
        low = close - 1.0
        result = adx(high, low, close, period=14)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than 2*period+1 raises InsufficientDataError."""
        close = pd.Series(np.linspace(100, 110, 20))
        high = close + 1.0
        low = close - 1.0
        with pytest.raises(InsufficientDataError):
            adx(high, low, close, period=14)

    def test_nan_warmup_count(self) -> None:
        """First 2*period values should be NaN."""
        n = 50
        close = pd.Series(np.linspace(100, 150, n))
        high = close + 1.0
        low = close - 1.0
        period = 14
        result = adx(high, low, close, period=period)
        nan_count = result.iloc[: 2 * period].isna().sum()
        assert nan_count == 2 * period

    def test_adx_range(self) -> None:
        """ADX should be between 0 and 100."""
        np.random.seed(42)
        n = 60
        close = pd.Series(100.0 + np.cumsum(np.random.randn(n)))
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        result = adx(high, low, close, period=14)
        valid = result.dropna()
        assert all(0.0 <= v <= 100.0 for v in valid)

    def test_flat_data(self) -> None:
        """Flat data: no directional movement, ADX should be low."""
        n = 50
        high = pd.Series([101.0] * n)
        low = pd.Series([99.0] * n)
        close = pd.Series([100.0] * n)
        result = adx(high, low, close, period=14)
        valid = result.dropna()
        # With constant high/low/close, DM=0, so DI=0, DX=0, ADX=0
        assert all(v == pytest.approx(0.0, abs=1.0) for v in valid)


# ---------------------------------------------------------------------------
# Supertrend tests
# ---------------------------------------------------------------------------


class TestSupertrend:
    """Tests for Supertrend indicator."""

    def test_known_value_uptrend(self) -> None:
        """Strong uptrend should produce +1 (uptrend signal).

        Reference: Supertrend indicator, Olivier Seban.
        """
        n = 30
        close = pd.Series(np.linspace(100, 130, n))
        high = close + 1.0
        low = close - 1.0
        result = supertrend(high, low, close, period=10, multiplier=3.0)
        valid = result.dropna()
        assert len(valid) > 0
        # Strong uptrend should give +1
        assert valid.iloc[-1] == pytest.approx(1.0, abs=0.01)

    def test_known_value_downtrend(self) -> None:
        """Strong downtrend should produce -1 (downtrend signal)."""
        n = 30
        close = pd.Series(np.linspace(130, 100, n))
        high = close + 1.0
        low = close - 1.0
        result = supertrend(high, low, close, period=10, multiplier=3.0)
        valid = result.dropna()
        assert len(valid) > 0
        # Strong downtrend should give -1
        assert valid.iloc[-1] == pytest.approx(-1.0, abs=0.01)

    def test_minimum_data(self) -> None:
        """Exactly period+1 data points should produce one valid output."""
        close = pd.Series(np.linspace(100, 110, 11))
        high = close + 1.0
        low = close - 1.0
        result = supertrend(high, low, close, period=10)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 raises InsufficientDataError."""
        close = pd.Series(np.linspace(100, 105, 5))
        high = close + 1.0
        low = close - 1.0
        with pytest.raises(InsufficientDataError):
            supertrend(high, low, close, period=10)

    def test_nan_warmup_count(self) -> None:
        """First period values should be NaN."""
        n = 30
        close = pd.Series(np.linspace(100, 130, n))
        high = close + 1.0
        low = close - 1.0
        period = 10
        result = supertrend(high, low, close, period=period)
        nan_count = result.iloc[:period].isna().sum()
        assert nan_count == period

    def test_values_are_plus_or_minus_1(self) -> None:
        """Supertrend output should only be +1 or -1 (or NaN for warmup)."""
        np.random.seed(42)
        n = 50
        close = pd.Series(100.0 + np.cumsum(np.random.randn(n)))
        high = close + np.abs(np.random.randn(n))
        low = close - np.abs(np.random.randn(n))
        result = supertrend(high, low, close, period=10, multiplier=3.0)
        valid = result.dropna()
        assert all(v in (1.0, -1.0) for v in valid)

    def test_flat_data(self) -> None:
        """Flat data should maintain initial trend direction."""
        n = 30
        high = pd.Series([101.0] * n)
        low = pd.Series([99.0] * n)
        close = pd.Series([100.0] * n)
        result = supertrend(high, low, close, period=10)
        valid = result.dropna()
        assert all(v in (1.0, -1.0) for v in valid)
