"""Extended volume indicator tests: _rolling_slope direct tests, edge cases.

_rolling_slope is a critical private helper used by obv_trend and ad_trend
but had no dedicated tests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.volume import _rolling_slope, ad_trend, obv_trend, relative_volume
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# _rolling_slope — direct tests
# ---------------------------------------------------------------------------


class TestRollingSlope:
    """Direct tests for the _rolling_slope private helper.

    Uses known regression slopes to verify mathematical correctness.
    Reference: Standard least-squares regression formula.
    """

    def test_linear_ascending_slope_one(self) -> None:
        """Series [0,1,2,3,4] with period=5 -> slope = 1.0."""
        series = pd.Series([0.0, 1.0, 2.0, 3.0, 4.0])
        result = _rolling_slope(series, period=5)
        assert result.iloc[-1] == pytest.approx(1.0, abs=1e-6)

    def test_linear_descending_slope_negative_one(self) -> None:
        """Series [4,3,2,1,0] with period=5 -> slope = -1.0."""
        series = pd.Series([4.0, 3.0, 2.0, 1.0, 0.0])
        result = _rolling_slope(series, period=5)
        assert result.iloc[-1] == pytest.approx(-1.0, abs=1e-6)

    def test_constant_series_slope_zero(self) -> None:
        """All-constant series -> slope = 0.0."""
        series = pd.Series([5.0] * 10)
        result = _rolling_slope(series, period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_nan_warmup_count(self) -> None:
        """First period-1 values should be NaN."""
        series = pd.Series(range(20), dtype=float)
        period = 5
        result = _rolling_slope(series, period=period)
        nan_count = result.iloc[: period - 1].isna().sum()
        assert nan_count == period - 1

    def test_period_two_minimal_case(self) -> None:
        """Period=2: slope between consecutive pairs."""
        # [0, 2, 4] -> slopes: NaN, 2.0, 2.0
        series = pd.Series([0.0, 2.0, 4.0])
        result = _rolling_slope(series, period=2)
        assert result.iloc[1] == pytest.approx(2.0, abs=1e-6)
        assert result.iloc[2] == pytest.approx(2.0, abs=1e-6)

    def test_slope_with_noise(self) -> None:
        """Longer series with general uptrend: all slopes positive."""
        np.random.seed(42)
        trend = np.arange(50, dtype=float) * 0.5
        noise = np.random.randn(50) * 0.1
        series = pd.Series(trend + noise)
        result = _rolling_slope(series, period=10)
        valid = result.dropna()
        # All slopes should be positive given the strong uptrend
        assert all(v > 0 for v in valid)

    def test_step_function_slope(self) -> None:
        """Step from 0 to 10: slope captures the step."""
        series = pd.Series([0.0] * 5 + [10.0] * 5)
        result = _rolling_slope(series, period=5)
        # Last window is all 10.0 -> slope = 0
        assert result.iloc[-1] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Additional obv_trend edge cases
# ---------------------------------------------------------------------------


class TestOBVTrendEdgeCases:
    """Edge cases for obv_trend not covered in the main test file."""

    def test_all_same_prices_zero_slope(self) -> None:
        """When all prices are identical, price_sign is 0, OBV is 0, slope is 0."""
        close = pd.Series([100.0] * 30)
        volume = pd.Series([1_000_000] * 30)
        result = obv_trend(close, volume, slope_period=20)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_zero_volume_zero_slope(self) -> None:
        """When volume is all zero, OBV is 0 everywhere."""
        close = pd.Series(range(25), dtype=float) + 100
        volume = pd.Series([0] * 25, dtype=float)
        result = obv_trend(close, volume, slope_period=20)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_insufficient_data(self) -> None:
        close = pd.Series([100.0] * 5)
        volume = pd.Series([1000] * 5, dtype=float)
        with pytest.raises(InsufficientDataError):
            obv_trend(close, volume, slope_period=20)


# ---------------------------------------------------------------------------
# Additional relative_volume edge cases
# ---------------------------------------------------------------------------


class TestRelativeVolumeEdgeCases:
    """Edge cases for relative_volume."""

    def test_constant_volume_ratio_one(self) -> None:
        """When volume is constant, RVOL = 1.0 after warmup."""
        volume = pd.Series([1_000_000] * 30, dtype=float)
        result = relative_volume(volume, period=20)
        valid = result.dropna()
        assert all(v == pytest.approx(1.0, abs=1e-6) for v in valid)

    def test_double_volume_ratio_two(self) -> None:
        """Volume doubles at the end -> RVOL approaches 2.0."""
        low = [500_000.0] * 19
        high = [1_000_000.0]
        volume = pd.Series(low + high)
        result = relative_volume(volume, period=20)
        # Last value: 1M / avg(19*500K + 1*1M) = 1M / 525K ≈ 1.905
        assert result.iloc[-1] > 1.5

    def test_insufficient_data(self) -> None:
        volume = pd.Series([1000.0] * 10)
        with pytest.raises(InsufficientDataError):
            relative_volume(volume, period=20)


# ---------------------------------------------------------------------------
# Additional ad_trend edge cases
# ---------------------------------------------------------------------------


class TestADTrendEdgeCases:
    """Edge cases for ad_trend."""

    def test_flat_bars_zero_slope(self) -> None:
        """When high == low, CLV is 0, AD is 0, slope is 0."""
        n = 25
        flat = pd.Series([100.0] * n)
        volume = pd.Series([1_000_000.0] * n)
        result = ad_trend(flat, flat, flat, volume, slope_period=20)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-6) for v in valid)

    def test_insufficient_data(self) -> None:
        n = 10
        s = pd.Series([100.0] * n)
        v = pd.Series([1000.0] * n)
        with pytest.raises(InsufficientDataError):
            ad_trend(s, s, s, v, slope_period=20)
