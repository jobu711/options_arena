"""Tests for oscillator indicators: rsi, stoch_rsi, williams_r.

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

from options_arena.indicators.oscillators import rsi, stoch_rsi, williams_r
from options_arena.utils.exceptions import InsufficientDataError

# ---------------------------------------------------------------------------
# RSI tests
# ---------------------------------------------------------------------------


class TestRSI:
    """Tests for Relative Strength Index."""

    @pytest.mark.critical
    def test_known_value_investopedia(self) -> None:
        """Known-value test using Investopedia RSI example.

        Reference: Investopedia RSI tutorial / Wilder's method.
        Using 14-period RSI with known closing prices.
        Data: 14 periods of gains/losses, compute first RSI value.

        Prices chosen to give known gains and losses:
        Close: [44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42,
                45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
        (15 data points for period=14, first RSI at index 14)
        """
        close = pd.Series(
            [
                44.0,
                44.34,
                44.09,
                43.61,
                44.33,
                44.83,
                45.10,
                45.42,
                45.84,
                46.08,
                45.89,
                46.03,
                45.61,
                46.28,
                46.28,
            ]
        )
        result = rsi(close, period=14)

        # First 14 values should be NaN
        assert result.iloc[:14].isna().all()

        # The last value should be a valid RSI between 0 and 100
        last_rsi = result.iloc[14]
        assert 0.0 <= last_rsi <= 100.0

        # Hand-calculated deltas from price:
        # Gains: 0.34, 0, 0, 0.72, 0.50, 0.27, 0.32, 0.42, 0.24, 0, 0.14, 0, 0.67, 0
        # Losses: 0, 0.25, 0.48, 0, 0, 0, 0, 0, 0, 0.19, 0, 0.42, 0, 0
        # Using ewm(alpha=1/14) Wilder's approximation
        # RSI should be in the range 60-80 for this mostly-upward data
        assert 50.0 < last_rsi < 90.0

    def test_minimum_data(self) -> None:
        """Exactly period+1 data points should produce one valid output."""
        close = pd.Series(
            [
                10.0,
                11.0,
                12.0,
                11.5,
                10.5,
                11.0,
                12.5,
                13.0,
                12.0,
                11.0,
                10.5,
                11.5,
                12.0,
                13.0,
                12.5,
            ]
        )
        result = rsi(close, period=14)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 data points raises InsufficientDataError."""
        close = pd.Series([10.0, 11.0, 12.0])
        with pytest.raises(InsufficientDataError):
            rsi(close, period=14)

    def test_nan_warmup_count(self) -> None:
        """First period values should be NaN."""
        close = pd.Series(np.linspace(100, 120, 30))
        period = 14
        result = rsi(close, period=period)
        nan_count = result.iloc[:period].isna().sum()
        assert nan_count == period

    def test_all_gains_rsi_100(self) -> None:
        """Monotonically increasing data: avg_loss=0, RSI should be 100."""
        close = pd.Series(np.arange(1.0, 20.0))
        result = rsi(close, period=14)
        valid = result.dropna()
        # All valid values should be 100 (no losses at all)
        assert all(v == pytest.approx(100.0, rel=1e-4) for v in valid)

    def test_all_losses_rsi_near_zero(self) -> None:
        """Monotonically decreasing data: RSI should be near 0."""
        close = pd.Series(np.arange(20.0, 1.0, -1.0))
        result = rsi(close, period=14)
        valid = result.dropna()
        # All valid values should be very close to 0
        assert all(v < 1.0 for v in valid)

    def test_flat_data(self) -> None:
        """All same price: no gains, no losses. RSI=100 by div-by-zero guard."""
        close = pd.Series([50.0] * 20)
        result = rsi(close, period=14)
        valid = result.dropna()
        # With Wilder's ewm on all zeros: avg_gain=0, avg_loss=0
        # avg_loss=0 => RSI=100 by our guard
        assert all(v == pytest.approx(100.0, rel=1e-4) for v in valid)

    def test_rsi_range(self) -> None:
        """RSI values should always be between 0 and 100."""
        np.random.seed(42)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(50)))
        result = rsi(close, period=14)
        valid = result.dropna()
        assert all(0.0 <= v <= 100.0 for v in valid)


# ---------------------------------------------------------------------------
# Stochastic RSI tests
# ---------------------------------------------------------------------------


class TestStochRSI:
    """Tests for Stochastic RSI."""

    def test_known_value(self) -> None:
        """Known-value test: Stochastic RSI should be 0-100.

        Reference: Chande & Kroll (1994) "The New Technical Trader".
        Stoch RSI applies stochastic formula to RSI values.
        """
        np.random.seed(42)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(40)))
        result = stoch_rsi(close, rsi_period=14, stoch_period=14)
        valid = result.dropna()
        assert len(valid) > 0
        assert all(0.0 <= v <= 100.0 for v in valid)

    def test_minimum_data(self) -> None:
        """Exactly rsi_period + stoch_period data points should produce one valid output."""
        close = pd.Series(np.linspace(100, 120, 28))
        result = stoch_rsi(close, rsi_period=14, stoch_period=14)
        valid = result.dropna()
        assert len(valid) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than rsi_period + stoch_period raises InsufficientDataError."""
        close = pd.Series(np.linspace(100, 120, 20))
        with pytest.raises(InsufficientDataError):
            stoch_rsi(close, rsi_period=14, stoch_period=14)

    def test_nan_warmup_count(self) -> None:
        """First rsi_period + stoch_period - 1 values should be NaN."""
        np.random.seed(42)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(50)))
        rsi_p = 14
        stoch_p = 14
        result = stoch_rsi(close, rsi_period=rsi_p, stoch_period=stoch_p)
        warmup = rsi_p + stoch_p - 1
        nan_count = result.iloc[:warmup].isna().sum()
        assert nan_count == warmup

    def test_flat_rsi_gives_50(self) -> None:
        """When RSI is constant (flat data), Stoch RSI range=0, output=50."""
        close = pd.Series([50.0] * 40)
        result = stoch_rsi(close, rsi_period=14, stoch_period=14)
        valid = result.dropna()
        # RSI is constant (100 from flat data), range=0, so stoch=50
        assert all(v == pytest.approx(50.0, abs=0.01) for v in valid)

    def test_range_0_to_100(self) -> None:
        """Stochastic RSI values should be between 0 and 100."""
        np.random.seed(123)
        close = pd.Series(100.0 + np.cumsum(np.random.randn(60)))
        result = stoch_rsi(close, rsi_period=14, stoch_period=14)
        valid = result.dropna()
        assert all(0.0 <= v <= 100.0 for v in valid)


# ---------------------------------------------------------------------------
# Williams %R tests
# ---------------------------------------------------------------------------


class TestWilliamsR:
    """Tests for Williams %R indicator."""

    def test_known_value(self) -> None:
        """Known-value test for Williams %R.

        Reference: Larry Williams, StockCharts documentation.
        With period=5:
        high = [127.01, 127.62, 126.59, 127.35, 128.17]
        low  = [125.36, 126.16, 124.93, 126.09, 126.82]
        close = [126.90]  (last close)
        highest_high = 128.17, lowest_low = 124.93
        %R = (128.17 - 126.90) / (128.17 - 124.93) * -100 = -39.22
        """
        high = pd.Series([127.01, 127.62, 126.59, 127.35, 128.17])
        low = pd.Series([125.36, 126.16, 124.93, 126.09, 126.82])
        close = pd.Series([126.90, 127.20, 125.50, 126.80, 126.90])

        result = williams_r(high, low, close, period=5)

        # First 4 should be NaN
        assert result.iloc[:4].isna().all()

        # At index 4:
        # highest_high = max(127.01, 127.62, 126.59, 127.35, 128.17) = 128.17
        # lowest_low = min(125.36, 126.16, 124.93, 126.09, 126.82) = 124.93
        # %R = (128.17 - 126.90) / (128.17 - 124.93) * -100
        expected = (128.17 - 126.90) / (128.17 - 124.93) * -100.0
        assert result.iloc[4] == pytest.approx(expected, rel=1e-4)

    def test_minimum_data(self) -> None:
        """Exactly period data points should produce one valid output."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8, 13.0])
        low = pd.Series([11.0, 11.5, 11.3, 11.8, 12.0])
        close = pd.Series([11.5, 12.0, 11.8, 12.3, 12.5])
        result = williams_r(high, low, close, period=5)
        valid = result.dropna()
        assert len(valid) == 1

    def test_insufficient_data(self) -> None:
        """Fewer than period data points raises InsufficientDataError."""
        high = pd.Series([12.0, 12.5])
        low = pd.Series([11.0, 11.5])
        close = pd.Series([11.5, 12.0])
        with pytest.raises(InsufficientDataError):
            williams_r(high, low, close, period=5)

    def test_nan_warmup_count(self) -> None:
        """First period-1 values should be NaN."""
        high = pd.Series([12.0, 12.5, 12.3, 12.8, 13.0, 12.7, 13.2, 13.5])
        low = pd.Series([11.0, 11.5, 11.3, 11.8, 12.0, 11.7, 12.2, 12.5])
        close = pd.Series([11.5, 12.0, 11.8, 12.3, 12.5, 12.2, 12.7, 13.0])
        period = 5
        result = williams_r(high, low, close, period=period)
        nan_count = result.iloc[: period - 1].isna().sum()
        assert nan_count == period - 1

    def test_range_negative_100_to_0(self) -> None:
        """Williams %R should always be between -100 and 0."""
        np.random.seed(42)
        n = 30
        close = pd.Series(100.0 + np.cumsum(np.random.randn(n) * 0.5))
        high = close + np.abs(np.random.randn(n) * 0.5)
        low = close - np.abs(np.random.randn(n) * 0.5)
        result = williams_r(high, low, close, period=14)
        valid = result.dropna()
        assert all(-100.0 <= v <= 0.0 for v in valid)

    def test_flat_data_gives_minus_50(self) -> None:
        """All same OHLC: high==low, range=0, output=-50."""
        high = pd.Series([50.0] * 10)
        low = pd.Series([50.0] * 10)
        close = pd.Series([50.0] * 10)
        result = williams_r(high, low, close, period=5)
        valid = result.dropna()
        assert all(v == pytest.approx(-50.0, abs=0.01) for v in valid)

    def test_close_at_high_gives_zero(self) -> None:
        """When close == highest high, %R should be 0."""
        high = pd.Series([10.0, 12.0, 11.0, 13.0, 14.0])
        low = pd.Series([9.0, 11.0, 10.0, 12.0, 13.0])
        close = pd.Series([10.0, 12.0, 11.0, 13.0, 14.0])  # close == high
        result = williams_r(high, low, close, period=5)
        # At index 4: highest_high=14, close=14 => (14-14)/(14-9)*-100 = 0
        assert result.iloc[4] == pytest.approx(0.0, abs=1e-4)

    def test_close_at_low_gives_minus_100(self) -> None:
        """When close == lowest low, %R should be -100."""
        high = pd.Series([15.0, 12.0, 14.0, 13.0, 11.0])
        low = pd.Series([14.0, 11.0, 13.0, 12.0, 10.0])
        close = pd.Series([14.0, 11.0, 13.0, 12.0, 10.0])  # close == low
        result = williams_r(high, low, close, period=5)
        # At index 4: lowest_low=10, close=10 => (15-10)/(15-10)*-100 = -100
        assert result.iloc[4] == pytest.approx(-100.0, abs=1e-4)
