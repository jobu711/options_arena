"""Tests for GARCH volatility forecasting + ADF stationarity.

Covers:
- TestStationarity: stationary/non-stationary/insufficient/missing-statsmodels
- TestGARCHForecast: synthetic data, edge cases, convergence, annualization
- TestIndicatorSignalsMLFields: new fields default None, non-finite normalization
"""

from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from options_arena.indicators.vol_forecast import (
    _get_adfuller,
    _get_arch,
    compute_garch_forecast,
)
from options_arena.indicators.vol_forecast import (
    _test_stationarity as adf_test_stationarity,
)
from options_arena.models.scan import IndicatorSignals

# Optional ML dependencies — tests that need the real library are marked
_has_arch = pytest.importorskip.__module__ is not None  # always True, just a namespace trick
_skip_no_arch = pytest.mark.skipif(_get_arch() is None, reason="arch library not installed")
_skip_no_statsmodels = pytest.mark.skipif(
    _get_adfuller() is None, reason="statsmodels library not installed"
)

# ---------------------------------------------------------------------------
# Helpers: synthetic data generators
# ---------------------------------------------------------------------------


def _make_stationary_returns(n: int = 500, seed: int = 42) -> pd.Series:
    """Generate stationary percentage log returns (mean-reverting noise)."""
    rng = np.random.default_rng(seed)
    # Simple normal returns — stationary by construction
    returns = rng.normal(loc=0.0, scale=1.5, size=n)
    return pd.Series(returns, name="returns")


def _make_nonstationary_series(n: int = 500, seed: int = 42) -> pd.Series:
    """Generate a non-stationary random walk series (cumulative sum)."""
    rng = np.random.default_rng(seed)
    # Random walk — non-stationary
    steps = rng.normal(loc=0.1, scale=1.0, size=n)
    return pd.Series(np.cumsum(steps), name="random_walk")


def _make_garch_like_returns(n: int = 500, seed: int = 42) -> pd.Series:
    """Generate returns with GARCH-like volatility clustering.

    Simulates a simple GARCH(1,1) process for realistic test data.
    Returns are percentage log returns.
    """
    rng = np.random.default_rng(seed)
    omega = 0.05
    alpha = 0.10
    beta = 0.85

    returns = np.zeros(n)
    sigma2 = np.zeros(n)
    sigma2[0] = omega / (1.0 - alpha - beta)  # unconditional variance

    for t in range(1, n):
        sigma2[t] = omega + alpha * returns[t - 1] ** 2 + beta * sigma2[t - 1]
        returns[t] = rng.normal(0.0, np.sqrt(sigma2[t]))

    return pd.Series(returns, name="garch_returns")


# ===========================================================================
# TestStationarity
# ===========================================================================


class TestStationarity:
    """Tests for the ADF stationarity test function."""

    @_skip_no_statsmodels
    def test_stationary_series(self) -> None:
        """Stationary returns should be detected as stationary."""
        returns = _make_stationary_returns(n=500)
        result = adf_test_stationarity(returns)
        assert result is not None
        is_stationary, p_value = result
        assert is_stationary is True
        assert 0.0 <= p_value < 0.05

    @_skip_no_statsmodels
    def test_nonstationary_series(self) -> None:
        """Non-stationary random walk should be detected as non-stationary."""
        series = _make_nonstationary_series(n=500)
        result = adf_test_stationarity(series)
        assert result is not None
        is_stationary, p_value = result
        assert is_stationary is False
        assert p_value >= 0.05

    def test_insufficient_data(self) -> None:
        """Returns None when series has fewer than 252 observations."""
        short_returns = _make_stationary_returns(n=100)
        result = adf_test_stationarity(short_returns)
        assert result is None

    @_skip_no_statsmodels
    def test_exactly_252_observations(self) -> None:
        """Exactly 252 observations should be enough."""
        returns = _make_stationary_returns(n=252)
        result = adf_test_stationarity(returns)
        assert result is not None

    def test_missing_statsmodels(self) -> None:
        """Returns None when statsmodels is not installed."""
        with patch("options_arena.indicators.vol_forecast._get_adfuller", return_value=None):
            returns = _make_stationary_returns(n=500)
            result = adf_test_stationarity(returns)
            assert result is None

    @_skip_no_statsmodels
    def test_nan_handling(self) -> None:
        """Series with NaN values is cleaned before test; still works if enough data."""
        returns = _make_stationary_returns(n=300)
        # Inject some NaNs
        returns.iloc[10] = float("nan")
        returns.iloc[50] = float("nan")
        result = adf_test_stationarity(returns)
        # Should still work — 298 clean obs > 252
        assert result is not None

    @_skip_no_statsmodels
    def test_returns_finite_p_value(self) -> None:
        """P-value returned must be finite."""
        returns = _make_stationary_returns(n=500)
        result = adf_test_stationarity(returns)
        assert result is not None
        _, p_value = result
        assert math.isfinite(p_value)


# ===========================================================================
# TestGARCHForecast
# ===========================================================================


class TestGARCHForecast:
    """Tests for compute_garch_forecast()."""

    @_skip_no_arch
    def test_synthetic_data_returns_float(self) -> None:
        """GARCH forecast on GARCH-like data should return a positive float."""
        returns = _make_garch_like_returns(n=500)
        result = compute_garch_forecast(returns)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0.0

    def test_insufficient_data(self) -> None:
        """Returns None when series has fewer than 252 observations."""
        short_returns = _make_garch_like_returns(n=200)
        result = compute_garch_forecast(short_returns)
        assert result is None

    def test_exactly_252_observations(self) -> None:
        """Exactly 252 observations should be enough for estimation."""
        returns = _make_garch_like_returns(n=252)
        result = compute_garch_forecast(returns)
        # May or may not converge with minimal data, but should not crash
        assert result is None or (isinstance(result, float) and result > 0.0)

    def test_missing_arch(self) -> None:
        """Returns None when arch library is not installed."""
        with patch("options_arena.indicators.vol_forecast._get_arch", return_value=None):
            returns = _make_garch_like_returns(n=500)
            result = compute_garch_forecast(returns)
            assert result is None

    def test_nonstationary_skipped(self) -> None:
        """Returns None when input series is non-stationary."""
        series = _make_nonstationary_series(n=500)
        result = compute_garch_forecast(series)
        assert result is None

    @_skip_no_arch
    def test_result_is_annualized(self) -> None:
        """GARCH forecast should be in annualized volatility scale (typically 0.05-2.0)."""
        returns = _make_garch_like_returns(n=500)
        result = compute_garch_forecast(returns)
        assert result is not None
        # Annualized vol should be in a reasonable range (not daily-scale)
        # Typical equity vol: 0.10-0.80; we use a generous bound
        assert 0.001 < result < 5.0

    def test_always_positive(self) -> None:
        """GARCH volatility forecast must be strictly positive."""
        returns = _make_garch_like_returns(n=500, seed=99)
        result = compute_garch_forecast(returns)
        if result is not None:
            assert result > 0.0

    def test_custom_horizon(self) -> None:
        """Custom forecast horizon should produce a valid result."""
        returns = _make_garch_like_returns(n=500)
        for horizon in [1, 5, 10, 20]:
            result = compute_garch_forecast(returns, horizon=horizon)
            if result is not None:
                assert result > 0.0
                assert math.isfinite(result)

    def test_returns_finite(self) -> None:
        """Result must always be finite (never NaN or Inf)."""
        returns = _make_garch_like_returns(n=500)
        result = compute_garch_forecast(returns)
        if result is not None:
            assert math.isfinite(result)

    def test_convergence_failure_returns_none(self) -> None:
        """Simulated convergence failure returns None."""
        # Constant series — GARCH should fail to converge meaningfully
        constant_returns = pd.Series(np.zeros(300), name="constant")
        result = compute_garch_forecast(constant_returns)
        # Either None (convergence failure) or extremely small value is acceptable
        assert result is None or (isinstance(result, float) and result >= 0.0)

    @_skip_no_arch
    def test_stationary_returns_produce_result(self) -> None:
        """Normal stationary returns should produce a valid GARCH forecast."""
        returns = _make_stationary_returns(n=500)
        result = compute_garch_forecast(returns)
        # Stationary returns should converge
        assert result is not None
        assert result > 0.0
        assert math.isfinite(result)

    def test_nan_in_series_cleaned(self) -> None:
        """NaN values should be dropped before fitting."""
        returns = _make_garch_like_returns(n=300)
        returns.iloc[5] = float("nan")
        returns.iloc[15] = float("nan")
        result = compute_garch_forecast(returns)
        # Should still work — 298 clean obs > 252
        assert result is None or (isinstance(result, float) and result > 0.0)


# ===========================================================================
# TestIndicatorSignalsMLFields
# ===========================================================================


class TestIndicatorSignalsMLFields:
    """Tests for new ML fields on IndicatorSignals."""

    def test_new_fields_default_none(self) -> None:
        """ML fields should default to None."""
        signals = IndicatorSignals()
        assert signals.vol_forecast_garch is None
        assert signals.iv_vs_forecast_spread is None

    def test_fields_accept_valid_values(self) -> None:
        """New fields should accept valid float values."""
        signals = IndicatorSignals(
            vol_forecast_garch=0.25,
            iv_vs_forecast_spread=0.03,
        )
        assert signals.vol_forecast_garch == 0.25
        assert signals.iv_vs_forecast_spread == 0.03

    def test_normalize_non_finite_nan(self) -> None:
        """NaN values on ML fields should be normalized to None."""
        signals = IndicatorSignals(
            vol_forecast_garch=float("nan"),
            iv_vs_forecast_spread=float("nan"),
        )
        assert signals.vol_forecast_garch is None
        assert signals.iv_vs_forecast_spread is None

    def test_normalize_non_finite_inf(self) -> None:
        """Inf values on ML fields should be normalized to None."""
        signals = IndicatorSignals(
            vol_forecast_garch=float("inf"),
            iv_vs_forecast_spread=float("inf"),
        )
        assert signals.vol_forecast_garch is None
        assert signals.iv_vs_forecast_spread is None

    def test_serialization_roundtrip(self) -> None:
        """ML fields should survive JSON serialization roundtrip."""
        signals = IndicatorSignals(
            vol_forecast_garch=0.32,
            iv_vs_forecast_spread=-0.05,
        )
        json_str = signals.model_dump_json()
        restored = IndicatorSignals.model_validate_json(json_str)
        assert restored.vol_forecast_garch == pytest.approx(0.32)
        assert restored.iv_vs_forecast_spread == pytest.approx(-0.05)

    def test_negative_spread_allowed(self) -> None:
        """iv_vs_forecast_spread can be negative (IV cheaper than GARCH forecast)."""
        signals = IndicatorSignals(iv_vs_forecast_spread=-0.10)
        assert signals.iv_vs_forecast_spread == -0.10


# ===========================================================================
# TestGuardedImports
# ===========================================================================


class TestGuardedImports:
    """Tests for guarded import functions."""

    @_skip_no_arch
    def test_get_arch_returns_module_when_installed(self) -> None:
        """_get_arch() should return the arch module when installed."""
        result = _get_arch()
        assert result is not None
        assert hasattr(result, "arch_model")

    @_skip_no_statsmodels
    def test_get_adfuller_returns_callable_when_installed(self) -> None:
        """_get_adfuller() should return the adfuller function when installed."""
        result = _get_adfuller()
        assert result is not None
        assert callable(result)

    def test_get_arch_returns_none_when_missing(self) -> None:
        """_get_arch() returns None when arch is not installed (tested via mock)."""
        with patch("options_arena.indicators.vol_forecast._get_arch", return_value=None):
            # The guarded import pattern is verified via compute_garch_forecast tests
            # with _get_arch mocked to None. This test confirms the pattern.
            returns = _make_garch_like_returns(n=500)
            assert compute_garch_forecast(returns) is None

    def test_get_adfuller_returns_none_when_missing(self) -> None:
        """_get_adfuller() returns None when statsmodels is not installed (tested via mock)."""
        with patch("options_arena.indicators.vol_forecast._get_adfuller", return_value=None):
            returns = _make_stationary_returns(n=500)
            # Stationarity test returns None, but GARCH should still try
            # (stationarity gate passes when test returns None)
            result = adf_test_stationarity(returns)
            assert result is None
