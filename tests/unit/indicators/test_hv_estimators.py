"""Tests for historical volatility estimators: Yang-Zhang.

The Yang-Zhang estimator is tested with:
- Known value verification (manual computation)
- Minimum data (exactly period+1 bars)
- Insufficient data (< period+1) returns None
- NaN guard (non-finite results return None)
- Flat prices (high==low every bar)
- Mismatched lengths -> ValueError
- All-NaN input -> None
- Annualization verification
"""

import math

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.hv_estimators import (
    compute_hv_yang_zhang,
)

# ---------------------------------------------------------------------------
# Helpers: generate synthetic OHLC data
# ---------------------------------------------------------------------------


def _make_ohlc(
    n: int = 50,
    seed: int = 42,
    daily_vol: float = 0.02,
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Generate synthetic OHLC data with known characteristics.

    Returns (open, high, low, close) Series.
    """
    rng = np.random.RandomState(seed)
    close_prices = 100.0 * np.exp(np.cumsum(rng.randn(n) * daily_vol))

    # Construct OHLC: open = prev close + small gap, high/low around close
    opens = np.empty(n)
    highs = np.empty(n)
    lows = np.empty(n)

    opens[0] = close_prices[0] * (1.0 + rng.randn() * 0.005)
    for i in range(1, n):
        opens[i] = close_prices[i - 1] * (1.0 + rng.randn() * 0.005)

    for i in range(n):
        intraday_range = abs(rng.randn()) * daily_vol * close_prices[i]
        highs[i] = max(opens[i], close_prices[i]) + intraday_range * 0.5
        lows[i] = min(opens[i], close_prices[i]) - intraday_range * 0.5
        # Ensure lows are positive
        lows[i] = max(lows[i], 0.01)
        # Ensure highs >= lows
        highs[i] = max(highs[i], lows[i])

    return (
        pd.Series(opens),
        pd.Series(highs),
        pd.Series(lows),
        pd.Series(close_prices),
    )


def _make_flat_ohlc(
    n: int = 30, price: float = 100.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """OHLC where all bars are flat: open=high=low=close."""
    arr = np.full(n, price)
    return pd.Series(arr), pd.Series(arr), pd.Series(arr), pd.Series(arr)


# ---------------------------------------------------------------------------
# Yang-Zhang estimator tests
# ---------------------------------------------------------------------------


class TestHVYangZhang:
    """Tests for compute_hv_yang_zhang."""

    def test_known_value(self) -> None:
        """Verify Yang-Zhang against manual computation.

        Reference: Yang & Zhang (2000) Eq. 6-12.
        sigma^2_yz = sigma^2_overnight + sigma^2_close + k * sigma^2_rs
        k = 0.34 / (1.34 + (n+1)/(n-1))
        sigma^2_close uses close-to-open (intraday) returns: ln(C_i / O_i)
        """
        # 6 bars, period=5
        opens = pd.Series([100.0, 102.0, 101.0, 103.0, 100.5, 104.0])
        highs = pd.Series([105.0, 106.0, 105.0, 107.0, 104.0, 108.0])
        lows = pd.Series([96.0, 98.0, 97.0, 99.0, 96.5, 100.0])
        closes = pd.Series([101.0, 103.0, 100.0, 104.0, 101.5, 105.0])

        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=5)
        assert result is not None

        # Manual computation
        n = 5
        # We use last (period+1)=6 bars
        o = opens.to_numpy(dtype=float)
        h = highs.to_numpy(dtype=float)
        l_arr = lows.to_numpy(dtype=float)
        c = closes.to_numpy(dtype=float)

        overnight = np.log(o[1:] / c[:-1])
        # Close-to-open (intraday) returns per Yang & Zhang (2000) Eq. 7
        close_ret = np.log(c[1:] / o[1:])

        overnight_mean = np.mean(overnight)
        sigma2_overnight = np.sum((overnight - overnight_mean) ** 2) / (n - 1)

        close_mean = np.mean(close_ret)
        sigma2_close = np.sum((close_ret - close_mean) ** 2) / (n - 1)

        # Rogers-Satchell on last n bars
        h_rs = h[1:]
        l_rs = l_arr[1:]
        o_rs = o[1:]
        c_rs = c[1:]
        log_hc = np.log(h_rs / c_rs)
        log_ho = np.log(h_rs / o_rs)
        log_lc = np.log(l_rs / c_rs)
        log_lo = np.log(l_rs / o_rs)
        sigma2_rs = np.sum(log_hc * log_ho + log_lc * log_lo) / n

        k = 0.34 / (1.34 + (n + 1) / (n - 1))
        # Per Yang & Zhang (2000) Eq. 12: weights are (1, 1, k)
        variance = sigma2_overnight + sigma2_close + k * sigma2_rs
        expected = math.sqrt(float(variance) * 252)

        assert result == pytest.approx(expected, rel=1e-6)

    def test_positive_result(self) -> None:
        """Yang-Zhang should return a positive value for volatile data."""
        opens, highs, lows, closes = _make_ohlc(50)
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)
        assert result is not None
        assert result > 0.0

    def test_annualized(self) -> None:
        """Result should be in reasonable annualized range."""
        opens, highs, lows, closes = _make_ohlc(50, daily_vol=0.01)
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)
        assert result is not None
        assert 0.05 < result < 1.0

    def test_minimum_data(self) -> None:
        """Exactly period+1 bars should work."""
        opens = pd.Series([100.0, 102.0, 101.0])
        highs = pd.Series([105.0, 106.0, 105.0])
        lows = pd.Series([96.0, 98.0, 97.0])
        closes = pd.Series([101.0, 103.0, 100.0])
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=2)
        assert result is not None

    def test_insufficient_data(self) -> None:
        """Fewer than period+1 bars should return None."""
        opens = pd.Series([100.0, 102.0])
        highs = pd.Series([105.0, 106.0])
        lows = pd.Series([96.0, 98.0])
        closes = pd.Series([101.0, 103.0])
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=5)
        assert result is None

    def test_flat_prices(self) -> None:
        """Flat OHLC: all variances are zero, result is zero."""
        opens, highs, lows, closes = _make_flat_ohlc(30)
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_mismatched_lengths(self) -> None:
        """Mismatched Series lengths should raise ValueError."""
        opens = pd.Series([100.0, 102.0, 101.0])
        highs = pd.Series([105.0, 106.0])
        lows = pd.Series([96.0, 98.0, 97.0])
        closes = pd.Series([101.0, 103.0, 100.0])
        with pytest.raises(ValueError, match="equal length"):
            compute_hv_yang_zhang(opens, highs, lows, closes, period=2)

    def test_nan_input_returns_none(self) -> None:
        """All-NaN input should return None."""
        nans = pd.Series([float("nan")] * 25)
        result = compute_hv_yang_zhang(nans, nans, nans, nans, period=20)
        assert result is None

    def test_k_parameter(self) -> None:
        """Verify the k mixing coefficient formula.

        k = 0.34 / (1.34 + (n+1)/(n-1))
        For n=20: k = 0.34 / (1.34 + 21/19) = 0.34 / (1.34 + 1.10526) ≈ 0.1390
        """
        n = 20
        k = 0.34 / (1.34 + (n + 1) / (n - 1))
        expected_k = 0.34 / (1.34 + 21.0 / 19.0)
        assert k == pytest.approx(expected_k, rel=1e-10)
        # k should be between 0 and 1
        assert 0.0 < k < 1.0
        assert k == pytest.approx(0.13903, rel=1e-3)

    def test_yang_zhang_vs_close_to_close(self) -> None:
        """Yang-Zhang should generally differ from simple close-to-close HV.

        Yang-Zhang uses more information (OHLC), so it should give a different
        estimate than just close-to-close, especially with gaps.
        """
        # Create data with significant overnight gaps
        rng = np.random.RandomState(123)
        n = 50
        closes = 100.0 * np.exp(np.cumsum(rng.randn(n) * 0.02))

        # Add large gaps
        opens = np.empty(n)
        opens[0] = closes[0] * 1.02
        for i in range(1, n):
            opens[i] = closes[i - 1] * (1.0 + rng.randn() * 0.015)

        highs = np.maximum(opens, closes) * (1.0 + np.abs(rng.randn(n)) * 0.01)
        lows = np.minimum(opens, closes) * (1.0 - np.abs(rng.randn(n)) * 0.01)
        lows = np.maximum(lows, 0.01)

        o_s = pd.Series(opens)
        h_s = pd.Series(highs)
        l_s = pd.Series(lows)
        c_s = pd.Series(closes)

        yz = compute_hv_yang_zhang(o_s, h_s, l_s, c_s, period=20)

        # Close-to-close HV
        log_returns = np.log(closes[-21:] / np.roll(closes[-21:], 1))[1:]
        cc_hv = float(np.std(log_returns, ddof=1)) * math.sqrt(252)

        assert yz is not None
        assert cc_hv > 0.0
        # They should both be positive but not identical
        assert yz > 0.0
        assert yz != pytest.approx(cc_hv, rel=0.01)

    def test_period_less_than_2_returns_none(self) -> None:
        """Period < 2 should return None (ddof=1 division by n-1=0)."""
        opens, highs, lows, closes = _make_ohlc(30)
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=1)
        assert result is None

    def test_zero_prices_returns_none(self) -> None:
        """Zero in prices should return None."""
        opens, highs, lows, closes = _make_ohlc(30)
        opens.iloc[-5] = 0.0
        result = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)
        assert result is None


# ---------------------------------------------------------------------------
# Cross-estimator comparison tests
# ---------------------------------------------------------------------------


class TestCrossEstimator:
    """Tests for Yang-Zhang estimator behavior."""

    def test_yang_zhang_positive_for_volatile_data(self) -> None:
        """Yang-Zhang should be positive for realistic volatile data."""
        opens, highs, lows, closes = _make_ohlc(50, daily_vol=0.02)

        yz = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)

        assert yz is not None and yz > 0.0

    def test_yang_zhang_zero_for_flat_data(self) -> None:
        """Yang-Zhang should return 0 for perfectly flat data."""
        opens, highs, lows, closes = _make_flat_ohlc(30)

        yz = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)

        assert yz is not None and yz == pytest.approx(0.0, abs=1e-10)

    def test_yang_zhang_finite(self) -> None:
        """Yang-Zhang should return finite values for normal data."""
        opens, highs, lows, closes = _make_ohlc(100, daily_vol=0.015)

        yz = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)

        assert yz is not None and math.isfinite(yz)

    def test_reasonable_range(self) -> None:
        """Yang-Zhang should produce values in a reasonable annualized range."""
        opens, highs, lows, closes = _make_ohlc(100, daily_vol=0.02)

        yz = compute_hv_yang_zhang(opens, highs, lows, closes, period=20)

        # With daily_vol ~0.02, annualized should be roughly 0.02 * sqrt(252) ≈ 0.317
        # Allow wide range for sampling variation
        assert yz is not None
        assert 0.05 < yz < 2.0, f"Estimator value {yz} out of reasonable range"

    def test_re_export_from_init(self) -> None:
        """Yang-Zhang estimator should be importable from the package."""
        from options_arena.indicators import (
            compute_hv_yang_zhang,
        )

        assert callable(compute_hv_yang_zhang)
