"""Tests for IV analytics indicators: 13 functions.

Each indicator is tested with:
- Happy path with realistic values
- Insufficient data / None inputs
- Edge cases (zero IV, flat data, boundary values)
- NaN/Inf rejection
"""

import math

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.iv_analytics import (
    classify_vol_regime,
    compute_call_skew,
    compute_ewma_vol_forecast,
    compute_expected_move,
    compute_expected_move_ratio,
    compute_hv_20d,
    compute_iv_hv_spread,
    compute_iv_term_shape,
    compute_iv_term_slope,
    compute_put_skew,
    compute_skew_ratio,
    compute_vix_correlation,
    compute_vol_cone_pctl,
)
from options_arena.models.enums import IVTermStructureShape, VolRegime

# ---------------------------------------------------------------------------
# compute_iv_hv_spread tests
# ---------------------------------------------------------------------------


class TestIVHVSpread:
    """Tests for compute_iv_hv_spread."""

    def test_positive_spread(self) -> None:
        """IV > HV produces positive spread."""
        result = compute_iv_hv_spread(0.30, 0.20)
        assert result is not None
        assert result == pytest.approx(0.10, rel=1e-6)

    def test_negative_spread(self) -> None:
        """IV < HV produces negative spread."""
        result = compute_iv_hv_spread(0.15, 0.25)
        assert result is not None
        assert result == pytest.approx(-0.10, rel=1e-6)

    def test_zero_spread(self) -> None:
        """Equal IV and HV produces zero spread."""
        result = compute_iv_hv_spread(0.25, 0.25)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_none_iv_returns_none(self) -> None:
        """None IV returns None."""
        assert compute_iv_hv_spread(None, 0.20) is None

    def test_none_hv_returns_none(self) -> None:
        """None HV returns None."""
        assert compute_iv_hv_spread(0.30, None) is None

    def test_both_none_returns_none(self) -> None:
        """Both None returns None."""
        assert compute_iv_hv_spread(None, None) is None

    def test_nan_iv_returns_none(self) -> None:
        """NaN IV returns None."""
        assert compute_iv_hv_spread(float("nan"), 0.20) is None

    def test_inf_hv_returns_none(self) -> None:
        """Inf HV returns None."""
        assert compute_iv_hv_spread(0.30, float("inf")) is None


# ---------------------------------------------------------------------------
# compute_hv_20d tests
# ---------------------------------------------------------------------------


class TestHV20d:
    """Tests for compute_hv_20d."""

    def test_known_value(self) -> None:
        """Computed HV should be positive for volatile data.

        Reference: Hull (2018), annualized std of log returns.
        Using 50 random prices with known seed.
        """
        np.random.seed(42)
        prices = 100.0 * np.exp(np.cumsum(np.random.randn(50) * 0.01))
        close = pd.Series(prices)
        result = compute_hv_20d(close)
        assert result is not None
        assert result > 0.0
        # Annualized vol should be roughly sqrt(252) * daily_std
        # With daily std ~0.01, annualized ~0.159
        assert 0.05 < result < 0.50

    def test_minimum_data(self) -> None:
        """Exactly 21 data points produces a valid result."""
        np.random.seed(42)
        prices = 100.0 * np.exp(np.cumsum(np.random.randn(21) * 0.01))
        close = pd.Series(prices)
        result = compute_hv_20d(close)
        assert result is not None
        assert result > 0.0

    def test_insufficient_data(self) -> None:
        """Fewer than 21 data points returns None."""
        close = pd.Series([100.0] * 20)
        result = compute_hv_20d(close)
        assert result is None

    def test_flat_data_zero_vol(self) -> None:
        """Flat prices produce zero or near-zero volatility."""
        close = pd.Series([100.0] * 25)
        result = compute_hv_20d(close)
        # Log returns of identical prices are 0, std is 0
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_uses_last_21_prices(self) -> None:
        """Only the last 21 prices are used for computation."""
        # First 30 prices are volatile, last 21 are flat
        volatile = pd.Series(np.linspace(100, 150, 30))
        flat = pd.Series([100.0] * 21)
        combined = pd.concat([volatile, flat], ignore_index=True)
        result = compute_hv_20d(combined)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)


# ---------------------------------------------------------------------------
# compute_iv_term_slope tests
# ---------------------------------------------------------------------------


class TestIVTermSlope:
    """Tests for compute_iv_term_slope."""

    def test_contango_positive_slope(self) -> None:
        """IV_60d > IV_30d produces positive (contango) slope."""
        result = compute_iv_term_slope(0.30, 0.25)
        assert result is not None
        assert result == pytest.approx(0.20, rel=1e-6)

    def test_backwardation_negative_slope(self) -> None:
        """IV_60d < IV_30d produces negative (backwardation) slope."""
        result = compute_iv_term_slope(0.20, 0.25)
        assert result is not None
        assert result == pytest.approx(-0.20, rel=1e-6)

    def test_flat_slope(self) -> None:
        """Equal IVs produce zero slope."""
        result = compute_iv_term_slope(0.25, 0.25)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_none_iv_60d_returns_none(self) -> None:
        """None IV_60d returns None."""
        assert compute_iv_term_slope(None, 0.25) is None

    def test_none_iv_30d_returns_none(self) -> None:
        """None IV_30d returns None."""
        assert compute_iv_term_slope(0.30, None) is None

    def test_zero_iv_30d_returns_none(self) -> None:
        """Zero IV_30d returns None (division by zero)."""
        assert compute_iv_term_slope(0.30, 0.0) is None

    def test_nan_input_returns_none(self) -> None:
        """NaN input returns None."""
        assert compute_iv_term_slope(float("nan"), 0.25) is None
        assert compute_iv_term_slope(0.30, float("nan")) is None

    def test_inf_input_returns_none(self) -> None:
        """Inf input returns None."""
        assert compute_iv_term_slope(float("inf"), 0.25) is None


# ---------------------------------------------------------------------------
# compute_iv_term_shape tests
# ---------------------------------------------------------------------------


class TestIVTermShape:
    """Tests for compute_iv_term_shape."""

    def test_contango(self) -> None:
        """Slope > 0.02 is CONTANGO."""
        assert compute_iv_term_shape(0.05) == IVTermStructureShape.CONTANGO

    def test_backwardation(self) -> None:
        """Slope < -0.02 is BACKWARDATION."""
        assert compute_iv_term_shape(-0.05) == IVTermStructureShape.BACKWARDATION

    def test_flat_positive_boundary(self) -> None:
        """Slope = 0.02 is FLAT (inclusive boundary)."""
        assert compute_iv_term_shape(0.02) == IVTermStructureShape.FLAT

    def test_flat_negative_boundary(self) -> None:
        """Slope = -0.02 is FLAT (inclusive boundary)."""
        assert compute_iv_term_shape(-0.02) == IVTermStructureShape.FLAT

    def test_flat_zero(self) -> None:
        """Slope = 0 is FLAT."""
        assert compute_iv_term_shape(0.0) == IVTermStructureShape.FLAT

    def test_none_returns_none(self) -> None:
        """None slope returns None."""
        assert compute_iv_term_shape(None) is None

    def test_nan_returns_none(self) -> None:
        """NaN slope returns None."""
        assert compute_iv_term_shape(float("nan")) is None

    def test_inf_returns_none(self) -> None:
        """Inf slope returns None."""
        assert compute_iv_term_shape(float("inf")) is None


# ---------------------------------------------------------------------------
# compute_put_skew tests
# ---------------------------------------------------------------------------


class TestPutSkew:
    """Tests for compute_put_skew."""

    def test_positive_skew(self) -> None:
        """OTM put IV > ATM IV produces positive skew (normal)."""
        result = compute_put_skew(0.35, 0.25)
        assert result is not None
        assert result == pytest.approx(0.40, rel=1e-6)

    def test_zero_skew(self) -> None:
        """Equal IVs produce zero skew."""
        result = compute_put_skew(0.25, 0.25)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_negative_skew(self) -> None:
        """OTM put IV < ATM IV produces negative skew (unusual)."""
        result = compute_put_skew(0.20, 0.25)
        assert result is not None
        assert result == pytest.approx(-0.20, rel=1e-6)

    def test_none_put_iv(self) -> None:
        """None put IV returns None."""
        assert compute_put_skew(None, 0.25) is None

    def test_none_atm_iv(self) -> None:
        """None ATM IV returns None."""
        assert compute_put_skew(0.35, None) is None

    def test_zero_atm_iv(self) -> None:
        """Zero ATM IV returns None (division by zero)."""
        assert compute_put_skew(0.35, 0.0) is None

    def test_nan_input(self) -> None:
        """NaN input returns None."""
        assert compute_put_skew(float("nan"), 0.25) is None

    def test_inf_input(self) -> None:
        """Inf input returns None."""
        assert compute_put_skew(float("inf"), 0.25) is None


# ---------------------------------------------------------------------------
# compute_call_skew tests
# ---------------------------------------------------------------------------


class TestCallSkew:
    """Tests for compute_call_skew."""

    def test_positive_skew(self) -> None:
        """OTM call IV > ATM IV produces positive skew."""
        result = compute_call_skew(0.30, 0.25)
        assert result is not None
        assert result == pytest.approx(0.20, rel=1e-6)

    def test_negative_skew(self) -> None:
        """OTM call IV < ATM IV produces negative skew (normal)."""
        result = compute_call_skew(0.22, 0.25)
        assert result is not None
        assert result == pytest.approx(-0.12, rel=1e-6)

    def test_none_inputs_return_none(self) -> None:
        """None inputs return None."""
        assert compute_call_skew(None, 0.25) is None
        assert compute_call_skew(0.30, None) is None

    def test_zero_atm_iv(self) -> None:
        """Zero ATM IV returns None (division by zero)."""
        assert compute_call_skew(0.30, 0.0) is None

    def test_nan_input(self) -> None:
        """NaN input returns None."""
        assert compute_call_skew(float("nan"), 0.25) is None


# ---------------------------------------------------------------------------
# compute_skew_ratio tests
# ---------------------------------------------------------------------------


class TestSkewRatio:
    """Tests for compute_skew_ratio."""

    def test_put_dominant(self) -> None:
        """Put IV > Call IV produces ratio > 1."""
        result = compute_skew_ratio(0.35, 0.25)
        assert result is not None
        assert result == pytest.approx(1.40, rel=1e-6)

    def test_call_dominant(self) -> None:
        """Call IV > Put IV produces ratio < 1."""
        result = compute_skew_ratio(0.20, 0.30)
        assert result is not None
        assert result == pytest.approx(2.0 / 3.0, rel=1e-6)

    def test_symmetric(self) -> None:
        """Equal IVs produce ratio = 1."""
        result = compute_skew_ratio(0.30, 0.30)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_none_inputs_return_none(self) -> None:
        """None inputs return None."""
        assert compute_skew_ratio(None, 0.25) is None
        assert compute_skew_ratio(0.30, None) is None

    def test_zero_call_iv(self) -> None:
        """Zero call IV returns None (division by zero)."""
        assert compute_skew_ratio(0.30, 0.0) is None

    def test_nan_input(self) -> None:
        """NaN input returns None."""
        assert compute_skew_ratio(float("nan"), 0.25) is None

    def test_inf_input(self) -> None:
        """Inf input returns None."""
        assert compute_skew_ratio(float("inf"), 0.25) is None


# ---------------------------------------------------------------------------
# classify_vol_regime tests
# ---------------------------------------------------------------------------


class TestClassifyVolRegime:
    """Tests for classify_vol_regime."""

    def test_low_regime(self) -> None:
        """IV rank < 25 is LOW."""
        assert classify_vol_regime(10.0) == VolRegime.LOW
        assert classify_vol_regime(0.0) == VolRegime.LOW
        assert classify_vol_regime(24.9) == VolRegime.LOW

    def test_normal_regime(self) -> None:
        """IV rank 25-50 is NORMAL."""
        assert classify_vol_regime(25.0) == VolRegime.NORMAL
        assert classify_vol_regime(40.0) == VolRegime.NORMAL
        assert classify_vol_regime(49.9) == VolRegime.NORMAL

    def test_elevated_regime(self) -> None:
        """IV rank 50-75 is ELEVATED."""
        assert classify_vol_regime(50.0) == VolRegime.ELEVATED
        assert classify_vol_regime(60.0) == VolRegime.ELEVATED
        assert classify_vol_regime(74.9) == VolRegime.ELEVATED

    def test_extreme_regime(self) -> None:
        """IV rank >= 75 is EXTREME."""
        assert classify_vol_regime(75.0) == VolRegime.EXTREME
        assert classify_vol_regime(90.0) == VolRegime.EXTREME
        assert classify_vol_regime(100.0) == VolRegime.EXTREME

    def test_none_returns_none(self) -> None:
        """None IV rank returns None."""
        assert classify_vol_regime(None) is None

    def test_nan_returns_none(self) -> None:
        """NaN IV rank returns None."""
        assert classify_vol_regime(float("nan")) is None

    def test_inf_returns_none(self) -> None:
        """Inf IV rank returns None."""
        assert classify_vol_regime(float("inf")) is None

    def test_boundary_values(self) -> None:
        """Exact boundary values are classified correctly."""
        assert classify_vol_regime(25.0) == VolRegime.NORMAL
        assert classify_vol_regime(50.0) == VolRegime.ELEVATED
        assert classify_vol_regime(75.0) == VolRegime.EXTREME


# ---------------------------------------------------------------------------
# compute_ewma_vol_forecast tests
# ---------------------------------------------------------------------------


class TestEWMAVolForecast:
    """Tests for compute_ewma_vol_forecast."""

    def test_positive_result(self) -> None:
        """EWMA forecast is positive for volatile returns.

        Reference: JP Morgan RiskMetrics (1996), lambda=0.94.
        """
        np.random.seed(42)
        returns = pd.Series(np.random.randn(50) * 0.01)
        result = compute_ewma_vol_forecast(returns)
        assert result is not None
        assert result > 0.0

    def test_annualized_scale(self) -> None:
        """Result is annualized (roughly sqrt(252) * daily vol)."""
        np.random.seed(42)
        daily_vol = 0.01
        returns = pd.Series(np.random.randn(100) * daily_vol)
        result = compute_ewma_vol_forecast(returns)
        assert result is not None
        # Should be in roughly the annualized range
        assert 0.05 < result < 0.50

    def test_minimum_data(self) -> None:
        """Exactly 20 data points produces a result."""
        np.random.seed(42)
        returns = pd.Series(np.random.randn(20) * 0.01)
        result = compute_ewma_vol_forecast(returns)
        assert result is not None

    def test_insufficient_data(self) -> None:
        """Fewer than 20 data points returns None."""
        returns = pd.Series(np.random.randn(19) * 0.01)
        result = compute_ewma_vol_forecast(returns)
        assert result is None

    def test_flat_returns_zero(self) -> None:
        """Flat returns produce zero or near-zero forecast."""
        returns = pd.Series([0.0] * 30)
        result = compute_ewma_vol_forecast(returns)
        assert result is not None
        assert result == pytest.approx(0.0, abs=1e-10)

    def test_custom_lambda(self) -> None:
        """Custom lambda parameter is respected."""
        np.random.seed(42)
        returns = pd.Series(np.random.randn(50) * 0.01)
        result_94 = compute_ewma_vol_forecast(returns, lambda_=0.94)
        result_80 = compute_ewma_vol_forecast(returns, lambda_=0.80)
        assert result_94 is not None
        assert result_80 is not None
        # Lower lambda -> more weight on recent observations -> different result
        assert result_94 != result_80

    def test_invalid_lambda_returns_none(self) -> None:
        """Invalid lambda returns None."""
        returns = pd.Series(np.random.randn(30) * 0.01)
        assert compute_ewma_vol_forecast(returns, lambda_=0.0) is None
        assert compute_ewma_vol_forecast(returns, lambda_=1.0) is None
        assert compute_ewma_vol_forecast(returns, lambda_=-0.5) is None
        assert compute_ewma_vol_forecast(returns, lambda_=float("nan")) is None

    def test_nan_in_returns_handled(self) -> None:
        """NaN values in returns are dropped before computation."""
        np.random.seed(42)
        raw = np.random.randn(50) * 0.01
        raw[5] = float("nan")
        raw[10] = float("nan")
        returns = pd.Series(raw)
        result = compute_ewma_vol_forecast(returns)
        # Should still produce a result since we have enough non-NaN values
        assert result is not None
        assert result > 0.0


# ---------------------------------------------------------------------------
# compute_vol_cone_pctl tests
# ---------------------------------------------------------------------------


class TestVolConePctl:
    """Tests for compute_vol_cone_pctl."""

    def test_median_percentile(self) -> None:
        """Value at the median of the distribution gives ~50th percentile."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 100))
        # Current HV at midpoint
        result = compute_vol_cone_pctl(0.30, hv_history)
        assert result is not None
        assert 40.0 < result < 60.0

    def test_low_percentile(self) -> None:
        """Value below most of the distribution gives low percentile."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 100))
        result = compute_vol_cone_pctl(0.12, hv_history)
        assert result is not None
        assert result < 10.0

    def test_high_percentile(self) -> None:
        """Value above most of the distribution gives high percentile."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 100))
        result = compute_vol_cone_pctl(0.48, hv_history)
        assert result is not None
        assert result > 90.0

    def test_none_hv_returns_none(self) -> None:
        """None current HV returns None."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 100))
        assert compute_vol_cone_pctl(None, hv_history) is None

    def test_nan_hv_returns_none(self) -> None:
        """NaN current HV returns None."""
        hv_history = pd.Series(np.linspace(0.10, 0.50, 100))
        assert compute_vol_cone_pctl(float("nan"), hv_history) is None

    def test_insufficient_history(self) -> None:
        """Fewer than 10 non-NaN observations returns None."""
        hv_history = pd.Series([0.20, 0.25, 0.30])
        assert compute_vol_cone_pctl(0.22, hv_history) is None

    def test_nan_in_history(self) -> None:
        """NaN values in history are dropped before counting."""
        data = np.linspace(0.10, 0.50, 15).tolist()
        data[5] = float("nan")
        data[10] = float("nan")
        hv_history = pd.Series(data)
        result = compute_vol_cone_pctl(0.30, hv_history)
        assert result is not None

    def test_all_nan_history_returns_none(self) -> None:
        """All-NaN history returns None."""
        hv_history = pd.Series([float("nan")] * 20)
        assert compute_vol_cone_pctl(0.30, hv_history) is None


# ---------------------------------------------------------------------------
# compute_vix_correlation tests
# ---------------------------------------------------------------------------


class TestVIXCorrelation:
    """Tests for compute_vix_correlation."""

    def test_negative_correlation(self) -> None:
        """Inversely correlated series produces negative correlation."""
        np.random.seed(42)
        ticker_returns = pd.Series(np.random.randn(60) * 0.01)
        # VIX typically moves opposite to stocks
        vix_changes = -ticker_returns + np.random.randn(60) * 0.002
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is not None
        assert result < 0.0

    def test_positive_correlation(self) -> None:
        """Positively correlated series produces positive correlation."""
        np.random.seed(42)
        ticker_returns = pd.Series(np.random.randn(60) * 0.01)
        vix_changes = pd.Series(ticker_returns.values + np.random.randn(60) * 0.001)
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is not None
        assert result > 0.0

    def test_correlation_bounds(self) -> None:
        """Correlation is bounded [-1, 1]."""
        np.random.seed(42)
        ticker_returns = pd.Series(np.random.randn(60) * 0.01)
        vix_changes = pd.Series(np.random.randn(60) * 0.01)
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is not None
        assert -1.0 <= result <= 1.0

    def test_insufficient_data(self) -> None:
        """Fewer than 60 data points returns None."""
        ticker_returns = pd.Series(np.random.randn(59) * 0.01)
        vix_changes = pd.Series(np.random.randn(59) * 0.01)
        assert compute_vix_correlation(ticker_returns, vix_changes) is None

    def test_mismatched_lengths(self) -> None:
        """Mismatched series lengths returns None."""
        ticker_returns = pd.Series(np.random.randn(60) * 0.01)
        vix_changes = pd.Series(np.random.randn(70) * 0.01)
        assert compute_vix_correlation(ticker_returns, vix_changes) is None

    def test_uses_last_60_observations(self) -> None:
        """Uses last 60 observations from longer series."""
        np.random.seed(42)
        # 100 observations, but function uses last 60
        ticker_returns = pd.Series(np.random.randn(100) * 0.01)
        vix_changes = pd.Series(-ticker_returns.values + np.random.randn(100) * 0.002)
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is not None

    def test_nan_handling(self) -> None:
        """NaN values are dropped before computing correlation."""
        np.random.seed(42)
        t_data = np.random.randn(60) * 0.01
        v_data = np.random.randn(60) * 0.01
        t_data[5] = float("nan")
        t_data[10] = float("nan")
        ticker_returns = pd.Series(t_data)
        vix_changes = pd.Series(v_data)
        result = compute_vix_correlation(ticker_returns, vix_changes)
        # Should work since we still have >= 30 non-NaN pairs
        assert result is not None

    def test_too_many_nans_returns_none(self) -> None:
        """Fewer than 30 non-NaN pairs returns None."""
        t_data = np.full(60, float("nan"))
        t_data[:20] = np.random.randn(20) * 0.01
        v_data = np.full(60, float("nan"))
        v_data[:20] = np.random.randn(20) * 0.01
        ticker_returns = pd.Series(t_data)
        vix_changes = pd.Series(v_data)
        result = compute_vix_correlation(ticker_returns, vix_changes)
        assert result is None


# ---------------------------------------------------------------------------
# compute_expected_move tests
# ---------------------------------------------------------------------------


class TestExpectedMove:
    """Tests for compute_expected_move."""

    def test_known_value(self) -> None:
        """Expected move = spot * iv * sqrt(dte / 365).

        Reference: CBOE expected move formula.
        spot=100, iv=0.30, dte=30 -> 100 * 0.30 * sqrt(30/365) = 8.596...
        """
        result = compute_expected_move(100.0, 0.30, 30)
        assert result is not None
        expected = 100.0 * 0.30 * math.sqrt(30 / 365)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_one_year_dte(self) -> None:
        """Full-year DTE: expected move = spot * iv."""
        result = compute_expected_move(100.0, 0.30, 365)
        assert result is not None
        assert result == pytest.approx(30.0, rel=1e-6)

    def test_none_iv_returns_none(self) -> None:
        """None IV returns None."""
        assert compute_expected_move(100.0, None, 30) is None

    def test_zero_iv_returns_none(self) -> None:
        """Zero IV returns None."""
        assert compute_expected_move(100.0, 0.0, 30) is None

    def test_zero_spot_returns_none(self) -> None:
        """Zero spot returns None."""
        assert compute_expected_move(0.0, 0.30, 30) is None

    def test_negative_spot_returns_none(self) -> None:
        """Negative spot returns None."""
        assert compute_expected_move(-100.0, 0.30, 30) is None

    def test_zero_dte_returns_none(self) -> None:
        """Zero DTE returns None."""
        assert compute_expected_move(100.0, 0.30, 0) is None

    def test_negative_dte_returns_none(self) -> None:
        """Negative DTE returns None."""
        assert compute_expected_move(100.0, 0.30, -5) is None

    def test_nan_spot_returns_none(self) -> None:
        """NaN spot returns None."""
        assert compute_expected_move(float("nan"), 0.30, 30) is None

    def test_nan_iv_returns_none(self) -> None:
        """NaN IV returns None."""
        assert compute_expected_move(100.0, float("nan"), 30) is None

    def test_inf_spot_returns_none(self) -> None:
        """Inf spot returns None."""
        assert compute_expected_move(float("inf"), 0.30, 30) is None


# ---------------------------------------------------------------------------
# compute_expected_move_ratio tests
# ---------------------------------------------------------------------------


class TestExpectedMoveRatio:
    """Tests for compute_expected_move_ratio."""

    def test_overpricing(self) -> None:
        """IV EM > actual EM -> ratio > 1."""
        result = compute_expected_move_ratio(10.0, 8.0)
        assert result is not None
        assert result == pytest.approx(1.25, rel=1e-6)

    def test_underpricing(self) -> None:
        """IV EM < actual EM -> ratio < 1."""
        result = compute_expected_move_ratio(6.0, 8.0)
        assert result is not None
        assert result == pytest.approx(0.75, rel=1e-6)

    def test_fair_pricing(self) -> None:
        """Equal EM -> ratio = 1."""
        result = compute_expected_move_ratio(8.0, 8.0)
        assert result is not None
        assert result == pytest.approx(1.0, rel=1e-6)

    def test_none_inputs_return_none(self) -> None:
        """None inputs return None."""
        assert compute_expected_move_ratio(None, 8.0) is None
        assert compute_expected_move_ratio(10.0, None) is None

    def test_zero_actual_returns_none(self) -> None:
        """Zero actual move returns None (division by zero)."""
        assert compute_expected_move_ratio(10.0, 0.0) is None

    def test_nan_input_returns_none(self) -> None:
        """NaN input returns None."""
        assert compute_expected_move_ratio(float("nan"), 8.0) is None
        assert compute_expected_move_ratio(10.0, float("nan")) is None

    def test_inf_input_returns_none(self) -> None:
        """Inf input returns None."""
        assert compute_expected_move_ratio(float("inf"), 8.0) is None
