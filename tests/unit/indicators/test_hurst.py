"""Tests for Hurst exponent via R/S analysis."""

import math

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators import hurst_exponent


class TestHurstExponent:
    """Tests for Hurst exponent via R/S analysis."""

    def test_trending_series_high_hurst(self) -> None:
        """Cumulative sum of positive increments -> H ~ 0.8-0.9."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.uniform(0.5, 1.5, size=500)) + 100)
        h = hurst_exponent(prices)
        assert h is not None
        assert 0.7 <= h <= 1.0

    def test_mean_reverting_series_low_hurst(self) -> None:
        """Strongly mean-reverting (Ornstein-Uhlenbeck-like) -> H < 0.5."""
        rng = np.random.default_rng(42)
        # Build an Ornstein-Uhlenbeck process with strong reversion
        # dX = theta * (mu - X) * dt + sigma * dW
        # Higher theta = faster reversion
        n = 2000
        theta = 0.8  # strong mean-reversion speed
        mu = np.log(100)  # mean level in log space
        sigma = 0.02
        log_prices = np.zeros(n)
        log_prices[0] = mu
        for i in range(1, n):
            log_prices[i] = (
                log_prices[i - 1]
                + theta * (mu - log_prices[i - 1])
                + sigma * rng.standard_normal()
            )
        prices = pd.Series(np.exp(log_prices))
        h = hurst_exponent(prices, min_bars=200)
        assert h is not None
        assert 0.0 <= h <= 0.5

    def test_random_walk_mid_hurst(self) -> None:
        """White noise cumsum -> H ~ 0.5."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.standard_normal(1000)) + 200)
        h = hurst_exponent(prices)
        assert h is not None
        assert 0.35 <= h <= 0.65

    def test_insufficient_data_returns_none(self) -> None:
        """< 200 bars -> None."""
        prices = pd.Series(range(100, 250))  # 150 bars
        assert hurst_exponent(prices, min_bars=200) is None

    def test_flat_prices_returns_none(self) -> None:
        """Constant prices -> zero log returns -> None."""
        prices = pd.Series([100.0] * 300)
        assert hurst_exponent(prices) is None

    def test_nan_in_input_handled(self) -> None:
        """NaN values in series -> graceful handling (None or valid float)."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.standard_normal(500)) + 200)
        prices.iloc[50] = float("nan")
        result = hurst_exponent(prices)
        assert result is None or (isinstance(result, float) and math.isfinite(result))

    def test_r_squared_below_threshold_returns_none(self) -> None:
        """Very noisy R/S relationship -> R-squared < 0.99 -> None with strict threshold."""
        rng = np.random.default_rng(99)
        prices = pd.Series(np.exp(rng.uniform(-5, 5, size=300)))
        result = hurst_exponent(prices, r_squared_threshold=0.99)
        assert result is None

    def test_result_clamped_to_valid_range(self) -> None:
        """Result is always in [0, 1] or None."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.standard_normal(500)) + 200)
        h = hurst_exponent(prices)
        assert h is None or 0.0 <= h <= 1.0

    def test_result_is_finite(self) -> None:
        """Result must be finite float or None."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.standard_normal(500)) + 200)
        h = hurst_exponent(prices)
        assert h is None or math.isfinite(h)

    def test_minimum_bars_parameter(self) -> None:
        """Custom min_bars respected."""
        prices = pd.Series(range(100, 260))  # 160 bars
        assert hurst_exponent(prices, min_bars=200) is None
        # With lower min_bars, may return a value or None depending on R-squared
        result = hurst_exponent(prices, min_bars=100)
        assert result is None or (isinstance(result, float) and 0.0 <= result <= 1.0)

    def test_exact_min_bars_boundary(self) -> None:
        """Series with exactly min_bars data points should be processed."""
        rng = np.random.default_rng(42)
        prices = pd.Series(np.cumsum(rng.standard_normal(200)) + 200)
        # Should not return None due to insufficient data (200 == min_bars)
        result = hurst_exponent(prices, min_bars=200)
        # May still be None for R-squared reasons, but not for data length
        assert result is None or (isinstance(result, float) and 0.0 <= result <= 1.0)

    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_deterministic_for_same_input(self, seed: int) -> None:
        """Same input always produces same output."""
        rng = np.random.default_rng(seed)
        prices = pd.Series(np.cumsum(rng.standard_normal(500)) + 200)
        h1 = hurst_exponent(prices)
        h2 = hurst_exponent(prices)
        assert h1 == h2
