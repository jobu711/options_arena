"""Tests for regime/macro indicator functions.

Tests for all 7 functions: market regime classification, VIX term structure,
risk-on/off, sector momentum, RS vs SPX, correlation regime shift, and
volume profile skew. Each function tested with:
1. Known-value / expected-behavior test
2. None/missing input test
3. Insufficient data test
4. Division-by-zero guard test
5. Edge cases
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.regime import (
    classify_market_regime,
    compute_correlation_regime_shift,
    compute_risk_on_off,
    compute_rs_vs_spx,
    compute_sector_momentum,
    compute_vix_term_structure,
    compute_volume_profile_skew,
)
from options_arena.models.enums import MarketRegime

# ---------------------------------------------------------------------------
# classify_market_regime tests
# ---------------------------------------------------------------------------


class TestClassifyMarketRegime:
    """Tests for market regime classification."""

    def test_crisis(self) -> None:
        """VIX >= 35 → CRISIS regardless of other inputs."""
        result = classify_market_regime(
            vix=40.0,
            vix_sma_20=25.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.5,
        )
        assert result == MarketRegime.CRISIS

    def test_crisis_at_boundary(self) -> None:
        """VIX exactly 35 → CRISIS."""
        result = classify_market_regime(
            vix=35.0,
            vix_sma_20=20.0,
            spx_returns_20d=0.0,
            spx_sma_slope=0.0,
        )
        assert result == MarketRegime.CRISIS

    def test_volatile(self) -> None:
        """VIX > 1.2 * VIX_SMA_20 → VOLATILE."""
        result = classify_market_regime(
            vix=28.0,
            vix_sma_20=20.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.VOLATILE

    def test_trending_bullish(self) -> None:
        """Strong positive SPX return + positive SMA slope → TRENDING."""
        result = classify_market_regime(
            vix=15.0,
            vix_sma_20=16.0,
            spx_returns_20d=0.05,
            spx_sma_slope=0.3,
        )
        assert result == MarketRegime.TRENDING

    def test_trending_bearish(self) -> None:
        """Strong negative SPX return + negative SMA slope → TRENDING."""
        result = classify_market_regime(
            vix=22.0,
            vix_sma_20=20.0,
            spx_returns_20d=-0.04,
            spx_sma_slope=-0.2,
        )
        assert result == MarketRegime.TRENDING

    def test_mean_reverting_default(self) -> None:
        """No strong signal → MEAN_REVERTING (default)."""
        result = classify_market_regime(
            vix=18.0,
            vix_sma_20=17.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_strong_return_conflicting_slope(self) -> None:
        """Strong positive return but negative slope → MEAN_REVERTING."""
        result = classify_market_regime(
            vix=15.0,
            vix_sma_20=16.0,
            spx_returns_20d=0.05,
            spx_sma_slope=-0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_zero_vix_sma(self) -> None:
        """Zero VIX SMA → skips volatile, falls through to mean reverting."""
        result = classify_market_regime(
            vix=15.0,
            vix_sma_20=0.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_nan_vix_returns_mean_reverting(self) -> None:
        """NaN VIX → MEAN_REVERTING (safe fallback, not silent misclassification)."""
        result = classify_market_regime(
            vix=float("nan"),
            vix_sma_20=20.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_nan_vix_sma_returns_mean_reverting(self) -> None:
        """NaN VIX SMA → MEAN_REVERTING."""
        result = classify_market_regime(
            vix=40.0,
            vix_sma_20=float("nan"),
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_nan_spx_returns_mean_reverting(self) -> None:
        """NaN SPX returns → MEAN_REVERTING."""
        result = classify_market_regime(
            vix=15.0,
            vix_sma_20=16.0,
            spx_returns_20d=float("nan"),
            spx_sma_slope=0.3,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_inf_vix_returns_mean_reverting(self) -> None:
        """Inf VIX → MEAN_REVERTING (not CRISIS)."""
        result = classify_market_regime(
            vix=float("inf"),
            vix_sma_20=20.0,
            spx_returns_20d=0.01,
            spx_sma_slope=0.1,
        )
        assert result == MarketRegime.MEAN_REVERTING

    def test_negative_inf_spx_slope_returns_mean_reverting(self) -> None:
        """Negative Inf SMA slope → MEAN_REVERTING."""
        result = classify_market_regime(
            vix=15.0,
            vix_sma_20=16.0,
            spx_returns_20d=0.05,
            spx_sma_slope=float("-inf"),
        )
        assert result == MarketRegime.MEAN_REVERTING


# ---------------------------------------------------------------------------
# compute_vix_term_structure tests
# ---------------------------------------------------------------------------


class TestVixTermStructure:
    """Tests for VIX term structure indicator."""

    def test_contango(self) -> None:
        """VIX3M > VIX → positive (contango, normal)."""
        result = compute_vix_term_structure(20.0, 25.0)
        assert result is not None
        assert result == pytest.approx(0.25, rel=1e-6)

    def test_backwardation(self) -> None:
        """VIX3M < VIX → negative (backwardation, fear)."""
        result = compute_vix_term_structure(25.0, 20.0)
        assert result is not None
        assert result == pytest.approx(-0.2, rel=1e-6)

    def test_flat(self) -> None:
        """VIX3M == VIX → 0.0 (flat)."""
        result = compute_vix_term_structure(20.0, 20.0)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_vix3m_none(self) -> None:
        """VIX3M unavailable → None."""
        assert compute_vix_term_structure(20.0, None) is None

    def test_zero_vix(self) -> None:
        """Zero VIX → None (division by zero)."""
        assert compute_vix_term_structure(0.0, 25.0) is None

    def test_inf_vix(self) -> None:
        """Infinity VIX → None."""
        assert compute_vix_term_structure(float("inf"), 25.0) is None

    def test_nan_vix3m(self) -> None:
        """NaN VIX3M → None."""
        assert compute_vix_term_structure(20.0, float("nan")) is None


# ---------------------------------------------------------------------------
# compute_risk_on_off tests
# ---------------------------------------------------------------------------


class TestRiskOnOff:
    """Tests for risk-on/off score."""

    def test_risk_on(self) -> None:
        """HYG outperforming LQD → positive (risk-on)."""
        result = compute_risk_on_off(0.02, 0.005)
        assert result is not None
        assert result == pytest.approx(0.015, rel=1e-6)

    def test_risk_off(self) -> None:
        """LQD outperforming HYG → negative (risk-off)."""
        result = compute_risk_on_off(-0.01, 0.01)
        assert result is not None
        assert result == pytest.approx(-0.02, rel=1e-6)

    def test_neutral(self) -> None:
        """Equal returns → 0.0."""
        result = compute_risk_on_off(0.01, 0.01)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_hyg_none(self) -> None:
        """None HYG → None."""
        assert compute_risk_on_off(None, 0.01) is None

    def test_lqd_none(self) -> None:
        """None LQD → None."""
        assert compute_risk_on_off(0.01, None) is None

    def test_both_none(self) -> None:
        """Both None → None."""
        assert compute_risk_on_off(None, None) is None

    def test_inf_input(self) -> None:
        """Infinity input → None."""
        assert compute_risk_on_off(float("inf"), 0.01) is None


# ---------------------------------------------------------------------------
# compute_sector_momentum tests
# ---------------------------------------------------------------------------


class TestSectorMomentum:
    """Tests for sector relative momentum."""

    def test_outperforming(self) -> None:
        """Sector > SPX → positive."""
        result = compute_sector_momentum(0.05, 0.02)
        assert result is not None
        assert result == pytest.approx(0.03, rel=1e-6)

    def test_underperforming(self) -> None:
        """Sector < SPX → negative."""
        result = compute_sector_momentum(0.01, 0.04)
        assert result is not None
        assert result == pytest.approx(-0.03, rel=1e-6)

    def test_inline(self) -> None:
        """Sector == SPX → 0.0."""
        result = compute_sector_momentum(0.03, 0.03)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_sector_none(self) -> None:
        """None sector return → None."""
        assert compute_sector_momentum(None, 0.02) is None

    def test_inf_spx(self) -> None:
        """Infinity SPX → None."""
        assert compute_sector_momentum(0.03, float("inf")) is None


# ---------------------------------------------------------------------------
# compute_rs_vs_spx tests
# ---------------------------------------------------------------------------


class TestRsVsSpx:
    """Tests for relative strength vs SPX."""

    def test_outperformance(self) -> None:
        """Ticker with higher cumulative returns → RS > 1.0."""
        np.random.seed(42)
        # Ticker returns: 0.5% daily avg, SPX: 0.2% daily avg
        ticker_returns = pd.Series(np.random.normal(0.005, 0.01, 100))
        spx_returns = pd.Series(np.random.normal(0.002, 0.01, 100))
        result = compute_rs_vs_spx(ticker_returns, spx_returns, period=60)
        assert result is not None
        assert result > 1.0  # ticker outperformed

    def test_underperformance(self) -> None:
        """Ticker with lower cumulative returns → RS < 1.0."""
        np.random.seed(42)
        ticker_returns = pd.Series(np.random.normal(-0.005, 0.01, 100))
        spx_returns = pd.Series(np.random.normal(0.005, 0.01, 100))
        result = compute_rs_vs_spx(ticker_returns, spx_returns, period=60)
        assert result is not None
        assert result < 1.0

    def test_insufficient_data(self) -> None:
        """Fewer than period bars → None."""
        ticker = pd.Series([0.01] * 30)
        spx = pd.Series([0.01] * 30)
        assert compute_rs_vs_spx(ticker, spx, period=60) is None

    def test_mismatched_lengths(self) -> None:
        """Mismatched lengths → ValueError."""
        ticker = pd.Series([0.01] * 100)
        spx = pd.Series([0.01] * 80)
        with pytest.raises(ValueError, match="equal length"):
            compute_rs_vs_spx(ticker, spx)

    def test_zero_spx_return(self) -> None:
        """SPX cumulative return of exactly -100% → None (denominator = 0)."""
        # All returns = -1.0 means (1 + r) product = 0
        spx = pd.Series([-1.0] + [0.0] * 59)
        ticker = pd.Series([0.01] * 60)
        result = compute_rs_vs_spx(ticker, spx, period=60)
        assert result is None

    def test_equal_returns(self) -> None:
        """Equal returns → RS ≈ 1.0."""
        returns = pd.Series([0.01] * 60)
        result = compute_rs_vs_spx(returns, returns.copy(), period=60)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-4)


# ---------------------------------------------------------------------------
# compute_correlation_regime_shift tests
# ---------------------------------------------------------------------------


class TestCorrelationRegimeShift:
    """Tests for correlation regime shift."""

    def test_increasing_correlation(self) -> None:
        """Short-window corr > long-window corr → positive (increasing).

        Build data where recent 20 bars are highly correlated to SPX
        but the 60-bar window includes uncorrelated data, making
        short-window correlation > long-window correlation.
        """
        np.random.seed(42)
        n = 150
        spx = pd.Series(np.random.normal(0, 1, n))
        # First 100 bars: uncorrelated noise.
        # Last 50 bars: nearly identical to SPX (high correlation).
        noise_early = np.random.normal(0, 1, 100)
        correlated_late = spx.iloc[100:].to_numpy() + np.random.normal(0, 0.05, 50)
        ticker = pd.Series(list(noise_early) + list(correlated_late))
        result = compute_correlation_regime_shift(
            ticker,
            spx,
            short_window=20,
            long_window=60,
        )
        assert result is not None
        # Last 20 bars (all correlated) vs last 60 bars (40 noise + 20 corr)
        # → short-window corr should exceed long-window corr
        assert result > 0

    def test_insufficient_data(self) -> None:
        """Fewer than long_window bars → None."""
        ticker = pd.Series([0.01] * 30)
        spx = pd.Series([0.01] * 30)
        assert compute_correlation_regime_shift(ticker, spx, long_window=60) is None

    def test_mismatched_lengths(self) -> None:
        """Mismatched lengths → ValueError."""
        ticker = pd.Series([0.01] * 100)
        spx = pd.Series([0.01] * 80)
        with pytest.raises(ValueError, match="equal length"):
            compute_correlation_regime_shift(ticker, spx)

    def test_flat_series(self) -> None:
        """Flat series → correlation is NaN → None."""
        ticker = pd.Series([1.0] * 100)
        spx = pd.Series([1.0] * 100)
        result = compute_correlation_regime_shift(ticker, spx)
        assert result is None

    def test_perfectly_correlated(self) -> None:
        """Identical series → both correlations ≈ 1.0, shift ≈ 0.0."""
        np.random.seed(42)
        data = pd.Series(np.random.normal(0, 1, 100))
        result = compute_correlation_regime_shift(data, data.copy())
        assert result is not None
        assert result == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# compute_volume_profile_skew tests
# ---------------------------------------------------------------------------


class TestVolumeProfileSkew:
    """Tests for volume profile skew."""

    def test_bullish_skew(self) -> None:
        """More volume at higher prices → positive skew."""
        close = pd.Series(
            [
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
                118,
                119,
            ]
        )
        # Heavy volume at higher prices
        volume = pd.Series(
            [
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
            ]
        )
        result = compute_volume_profile_skew(close, volume)
        assert result is not None
        assert result > 0  # bullish skew

    def test_bearish_skew(self) -> None:
        """More volume at lower prices → negative skew."""
        close = pd.Series(
            [
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
                118,
                119,
            ]
        )
        # Heavy volume at lower prices
        volume = pd.Series(
            [
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                500,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
                100,
            ]
        )
        result = compute_volume_profile_skew(close, volume)
        assert result is not None
        assert result < 0  # bearish skew

    def test_even_volume(self) -> None:
        """Even volume distribution → near-zero skew."""
        close = pd.Series(
            [
                100,
                101,
                102,
                103,
                104,
                105,
                106,
                107,
                108,
                109,
                110,
                111,
                112,
                113,
                114,
                115,
                116,
                117,
                118,
                119,
            ]
        )
        volume = pd.Series([100] * 20)
        result = compute_volume_profile_skew(close, volume)
        assert result is not None
        # VWAP == simple avg with uniform volume → skew ≈ 0
        assert result == pytest.approx(0.0, abs=0.01)

    def test_insufficient_data(self) -> None:
        """Fewer than period bars → None."""
        close = pd.Series([100.0] * 10)
        volume = pd.Series([1000] * 10)
        assert compute_volume_profile_skew(close, volume, period=20) is None

    def test_zero_volume(self) -> None:
        """All zero volume → None."""
        close = pd.Series([100.0] * 20)
        volume = pd.Series([0] * 20)
        assert compute_volume_profile_skew(close, volume) is None

    def test_mismatched_lengths(self) -> None:
        """Mismatched lengths → ValueError."""
        close = pd.Series([100.0] * 25)
        volume = pd.Series([100] * 20)
        with pytest.raises(ValueError, match="equal length"):
            compute_volume_profile_skew(close, volume)

    def test_flat_prices(self) -> None:
        """Flat prices → VWAP == avg → skew = 0."""
        close = pd.Series([100.0] * 20)
        volume = pd.Series([500, 100] * 10)
        result = compute_volume_profile_skew(close, volume)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-9)
