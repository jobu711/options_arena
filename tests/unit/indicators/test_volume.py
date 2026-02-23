"""Tests for volume indicators: obv_trend, relative_volume, ad_trend.

Every indicator is tested with all five required test types:
1. Known-value test (with source citation)
2. Minimum data test
3. Insufficient data test
4. NaN warmup test
5. Edge cases (flat, monotonic, zero volume)
"""

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.volume import ad_trend, obv_trend, relative_volume
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# obv_trend tests
# ---------------------------------------------------------------------------


class TestOBVTrend:
    """Tests for On-Balance Volume trend indicator."""

    def test_known_value(self) -> None:
        """Known-value test: OBV trend for monotonically rising prices.

        Reference: Granville (1963) "New Key to Stock Market Profits".
        When prices rise every day with constant volume, OBV rises linearly,
        so the slope should be approximately equal to the volume.
        """
        n = 25
        close = pd.Series(np.arange(100.0, 100.0 + n))
        volume = pd.Series([1000.0] * n)
        result = obv_trend(close, volume, slope_period=5)

        valid = result.dropna()
        assert len(valid) > 0
        # All up days with vol=1000 => OBV increases by 1000 each day
        # Slope should be ~1000
        assert all(v == pytest.approx(1000.0, rel=0.01) for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly slope_period+1 data points should produce at least one valid output."""
        close = pd.Series([10.0, 11.0, 12.0, 11.5, 12.5, 13.0])
        volume = pd.Series([100.0, 150.0, 200.0, 100.0, 250.0, 300.0])
        result = obv_trend(close, volume, slope_period=5)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than slope_period+1 raises InsufficientDataError."""
        close = pd.Series([10.0, 11.0])
        volume = pd.Series([100.0, 150.0])
        with pytest.raises(InsufficientDataError):
            obv_trend(close, volume, slope_period=5)

    def test_nan_warmup(self) -> None:
        """Verify NaN count in warmup period."""
        n = 30
        close = pd.Series(np.linspace(100, 110, n))
        volume = pd.Series([1000.0] * n)
        slope_period = 10
        result = obv_trend(close, volume, slope_period=slope_period)
        # Rolling window produces NaN for first slope_period-1 values,
        # plus diff produces NaN at index 0
        nan_count = result.isna().sum()
        assert nan_count >= slope_period - 1

    def test_flat_price(self) -> None:
        """Flat price: sign(diff)=0 after first, OBV stays at 0, slope=0."""
        close = pd.Series([50.0] * 25)
        volume = pd.Series([1000.0] * 25)
        result = obv_trend(close, volume, slope_period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-4) for v in valid)

    def test_zero_volume(self) -> None:
        """Zero volume: OBV stays at 0 regardless of price, slope=0."""
        close = pd.Series(np.linspace(100, 120, 25))
        volume = pd.Series([0.0] * 25)
        result = obv_trend(close, volume, slope_period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-4) for v in valid)


# ---------------------------------------------------------------------------
# relative_volume tests
# ---------------------------------------------------------------------------


class TestRelativeVolume:
    """Tests for relative volume indicator."""

    def test_known_value(self) -> None:
        """Known-value test: constant volume should give RVOL=1.0.

        Reference: Standard relative volume definition.
        volume / SMA(volume) = 1.0 when volume is constant.
        """
        volume = pd.Series([1000.0] * 25)
        result = relative_volume(volume, period=20)
        valid = result.dropna()
        assert all(v == pytest.approx(1.0, rel=1e-4) for v in valid)

    def test_double_volume(self) -> None:
        """Volume spike: last value is 2x average."""
        volume = pd.Series([1000.0] * 20 + [2000.0])
        result = relative_volume(volume, period=20)
        # Last value: 2000 / avg(first 20 = 1000, plus shift to include 2000)
        # At index 20, SMA is over indices 1-20 = (19*1000 + 2000)/20 = 1050
        # RVOL = 2000/1050
        assert result.iloc[-1] == pytest.approx(2000.0 / 1050.0, rel=1e-4)

    def test_minimum_data(self) -> None:
        """Exactly period data points should produce one valid output."""
        volume = pd.Series([100.0, 200.0, 150.0, 250.0, 300.0])
        result = relative_volume(volume, period=5)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than period data points raises InsufficientDataError."""
        volume = pd.Series([100.0, 200.0])
        with pytest.raises(InsufficientDataError):
            relative_volume(volume, period=5)

    def test_nan_warmup_count(self) -> None:
        """First period-1 values should be NaN."""
        volume = pd.Series([1000.0] * 25)
        period = 10
        result = relative_volume(volume, period=period)
        nan_count = result.iloc[: period - 1].isna().sum()
        assert nan_count == period - 1

    def test_zero_volume_guard(self) -> None:
        """Zero average volume should not crash (produces NaN)."""
        volume = pd.Series([0.0] * 25)
        result = relative_volume(volume, period=10)
        # 0/0 = NaN, which is fine
        valid = result.dropna()
        assert len(valid) == 0 or all(np.isfinite(v) for v in valid)


# ---------------------------------------------------------------------------
# ad_trend tests
# ---------------------------------------------------------------------------


class TestADTrend:
    """Tests for Accumulation/Distribution line trend."""

    def test_known_value(self) -> None:
        """Known-value test: close at high => CLV=1, positive AD line.

        Reference: Marc Chaikin, Accumulation/Distribution definition.
        When close == high: CLV = ((high-low) - 0) / (high-low) = 1
        AD increases by volume each bar.
        """
        n = 25
        high = pd.Series([110.0] * n)
        low = pd.Series([100.0] * n)
        close = pd.Series([110.0] * n)  # close == high => CLV = 1.0
        volume = pd.Series([1000.0] * n)
        result = ad_trend(high, low, close, volume, slope_period=5)
        valid = result.dropna()
        # CLV=1, so AD_i = i * 1000. Slope over 5 bars = 1000.
        assert all(v == pytest.approx(1000.0, rel=0.01) for v in valid)

    def test_close_at_low_negative(self) -> None:
        """When close == low, CLV = -1, AD line decreases."""
        n = 25
        high = pd.Series([110.0] * n)
        low = pd.Series([100.0] * n)
        close = pd.Series([100.0] * n)  # close == low => CLV = -1.0
        volume = pd.Series([1000.0] * n)
        result = ad_trend(high, low, close, volume, slope_period=5)
        valid = result.dropna()
        # CLV=-1, so AD decreases by 1000 each bar. Slope = -1000.
        assert all(v == pytest.approx(-1000.0, rel=0.01) for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly slope_period data points should produce at least one valid output."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8, 13.0])
        low = pd.Series([11.0, 11.5, 11.3, 11.8, 12.0])
        close = pd.Series([11.5, 12.0, 11.8, 12.3, 12.5])
        volume = pd.Series([1000.0, 1500.0, 2000.0, 1000.0, 2500.0])
        result = ad_trend(high, low, close, volume, slope_period=5)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than slope_period data points raises InsufficientDataError."""
        high = pd.Series([12.0, 12.5])
        low = pd.Series([11.0, 11.5])
        close = pd.Series([11.5, 12.0])
        volume = pd.Series([1000.0, 1500.0])
        with pytest.raises(InsufficientDataError):
            ad_trend(high, low, close, volume, slope_period=5)

    def test_nan_warmup(self) -> None:
        """Verify NaN values in warmup period."""
        n = 30
        close = pd.Series(np.linspace(100, 110, n))
        high = close + 2.0
        low = close - 2.0
        volume = pd.Series([1000.0] * n)
        slope_period = 10
        result = ad_trend(high, low, close, volume, slope_period=slope_period)
        nan_count = result.isna().sum()
        assert nan_count >= slope_period - 1

    def test_high_equals_low_guard(self) -> None:
        """When high == low (flat bar), CLV = 0 (div-by-zero guard)."""
        n = 25
        high = pd.Series([100.0] * n)
        low = pd.Series([100.0] * n)
        close = pd.Series([100.0] * n)
        volume = pd.Series([1000.0] * n)
        result = ad_trend(high, low, close, volume, slope_period=5)
        valid = result.dropna()
        # CLV=0, AD stays at 0, slope=0
        assert all(v == pytest.approx(0.0, abs=1e-4) for v in valid)

    def test_zero_volume(self) -> None:
        """Zero volume: AD line stays at 0."""
        n = 25
        high = pd.Series([110.0] * n)
        low = pd.Series([100.0] * n)
        close = pd.Series([105.0] * n)
        volume = pd.Series([0.0] * n)
        result = ad_trend(high, low, close, volume, slope_period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(0.0, abs=1e-4) for v in valid)
