"""GARCH volatility forecasting + ADF stationarity testing.

Uses ``arch`` library for GARCH(1,1) h-step-ahead volatility forecasts,
with ``statsmodels`` ADF test as a stationarity gate. GARCH is the sole
parametric volatility forecaster.

Rules:
- Takes pandas Series inputs, returns float | None or tuple.
- NO Pydantic models, NO API calls -- pure math on pre-fetched data.
- Guarded imports: returns None when ``arch`` or ``statsmodels`` not installed.
- Return ``None`` on insufficient data (<252 obs), convergence failure, or non-stationarity.
- All volatility results annualized with sqrt(252).
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Minimum observations required for GARCH estimation (1 year of trading days)
_MIN_OBSERVATIONS: int = 252

# ADF p-value threshold for stationarity (5% significance level)
_ADF_P_VALUE_THRESHOLD: float = 0.05

# Trading days per year for annualization
_TRADING_DAYS: int = 252


def _get_arch() -> Any:  # noqa: ANN401
    """Attempt to import the ``arch`` library. Returns module or ``None``."""
    try:
        import arch

        return arch
    except ImportError:
        logger.info("arch library not installed -- GARCH features disabled")
        return None


def _get_adfuller() -> Any:  # noqa: ANN401
    """Attempt to import ``adfuller`` from statsmodels. Returns callable or ``None``."""
    try:
        from statsmodels.tsa.stattools import adfuller

        return adfuller
    except ImportError:
        logger.info("statsmodels not installed -- ADF stationarity test disabled")
        return None


def test_stationarity(returns: pd.Series) -> tuple[bool, float] | None:
    """Augmented Dickey-Fuller stationarity test on a returns series.

    Null hypothesis: the series has a unit root (non-stationary).
    Rejection (p < 0.05) indicates stationarity.

    Reference: Dickey, D.A. & Fuller, W.A. (1979) "Distribution of the
    Estimators for Autoregressive Time Series With a Unit Root", JASA, 74(366).

    Args:
        returns: Daily log returns series. Requires at least 252 observations.

    Returns:
        Tuple of (is_stationary, p_value) where is_stationary is True when
        p_value < 0.05, or ``None`` if insufficient data or statsmodels missing.
    """
    adfuller = _get_adfuller()
    if adfuller is None:
        return None

    clean = returns.dropna()
    if len(clean) < _MIN_OBSERVATIONS:
        return None

    try:
        result = adfuller(clean.to_numpy())
        # adfuller returns: (adf_stat, p_value, usedlag, nobs, critical_values, icbest)
        p_value: float = float(result[1])
        if not math.isfinite(p_value):
            return None
        is_stationary = p_value < _ADF_P_VALUE_THRESHOLD
        return (is_stationary, p_value)
    except Exception:
        logger.warning("ADF stationarity test failed", exc_info=True)
        return None


def compute_garch_forecast(
    returns: pd.Series,
    p: int = 1,
    q: int = 1,
    horizon: int = 1,
) -> float | None:
    """GARCH(p,q) h-step-ahead volatility forecast.

    Fits a GARCH(1,1) model to percentage log returns, then forecasts
    variance ``horizon`` steps ahead. Returns annualized volatility.

    Reference: Bollerslev, T. (1986) "Generalized Autoregressive Conditional
    Heteroskedasticity", Journal of Econometrics, 31(3), 307-327.

    Args:
        returns: Daily percentage log returns (i.e., log(P_t/P_{t-1}) * 100).
            Requires at least 252 observations.
        p: GARCH lag order for conditional variance (default 1).
        q: ARCH lag order for squared residuals (default 1).
        horizon: Forecast horizon in trading days (default 1).

    Returns:
        Annualized volatility forecast as float, or ``None`` if insufficient
        data, convergence failure, non-stationarity, or missing arch library.
    """
    arch_mod = _get_arch()
    if arch_mod is None:
        return None

    clean = returns.dropna()
    if len(clean) < _MIN_OBSERVATIONS:
        return None

    # Stationarity gate: GARCH requires stationary returns
    stationarity = test_stationarity(clean)
    if stationarity is not None and not stationarity[0]:
        logger.debug("GARCH skipped: returns are non-stationary (p=%.4f)", stationarity[1])
        return None

    try:
        model = arch_mod.arch_model(clean, vol="GARCH", p=p, q=q)
        res = model.fit(disp="off")

        # Check convergence: flag != 0 means failure
        if res.convergence_flag != 0:
            logger.debug("GARCH convergence failed (flag=%d)", res.convergence_flag)
            return None

        # Forecast variance h steps ahead
        forecasts = res.forecast(horizon=horizon)
        variance_df = forecasts.variance

        # Last row contains the h-step forecasts; take the furthest horizon column
        last_row = variance_df.iloc[-1]
        # Columns are h.1, h.2, ..., h.N — take the last column (h.horizon)
        forecast_variance = float(last_row.iloc[-1])

        if not math.isfinite(forecast_variance) or forecast_variance <= 0.0:
            return None

        # Convert from percentage returns variance to decimal and annualize
        # Returns are in percentage form (multiplied by 100), so variance is in %^2
        # Divide by 10000 to get decimal variance, then annualize
        annualized_vol = math.sqrt(forecast_variance / 10000.0 * _TRADING_DAYS)

        if not math.isfinite(annualized_vol) or annualized_vol <= 0.0:
            return None

        return annualized_vol

    except Exception:
        logger.warning("GARCH forecast computation failed", exc_info=True)
        return None
