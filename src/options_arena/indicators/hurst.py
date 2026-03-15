"""Hurst exponent via rescaled range (R/S) analysis.

Classifies a time series as trending (H > 0.5), mean-reverting (H < 0.5),
or random walk (H ~ 0.5) using rescaled range analysis (Mandelbrot & Wallis, 1969).

Rules:
- Takes pandas Series input (close prices), returns float | None.
- NO Pydantic models, NO API calls — pure math on pre-fetched data.
- Returns ``None`` on insufficient data, unreliable fit, or non-finite result.
"""

import math

import numpy as np
import pandas as pd


def hurst_exponent(
    close: pd.Series,
    min_bars: int = 200,
    max_lag: int = 100,
    r_squared_threshold: float = 0.5,
) -> float | None:
    """Compute the Hurst exponent via rescaled range (R/S) analysis.

    For each lag size, the return series is divided into non-overlapping windows.
    Within each window the rescaled range R/S is computed, then averaged across
    windows. An OLS regression of log(R/S) vs log(lag) gives the Hurst exponent
    as the slope.

    Formula:
        H = slope of OLS(log(mean_RS), log(lag)) for lag in [10, max_lag)

    Reference: Mandelbrot, B.B. & Wallis, J.R. (1969) "Robustness of the
    Rescaled Range R/S in the Measurement of Noncyclic Long Run Statistical
    Dependence", Water Resources Research, 5(5), 967-988.

    Args:
        close: Daily close prices. Requires at least ``min_bars`` data points.
        min_bars: Minimum number of close prices required (default 200).
        max_lag: Maximum lag for R/S computation (default 100).
        r_squared_threshold: Minimum R-squared for the OLS fit (default 0.5).
            Below this threshold the result is deemed unreliable and ``None``
            is returned.

    Returns:
        Hurst exponent clamped to [0.0, 1.0], or ``None`` if data is
        insufficient, all-constant, or the OLS fit is unreliable.
    """
    if len(close) < min_bars:
        return None

    # Drop NaN values and convert to numpy
    clean: np.ndarray = close.dropna().to_numpy(dtype=float)

    if len(clean) < min_bars:
        return None

    # Guard: all values must be positive for log returns
    if np.any(clean <= 0.0):
        return None

    # Compute log returns
    log_returns: np.ndarray = np.diff(np.log(clean))

    if len(log_returns) == 0:
        return None

    # Guard: if all log returns are zero (constant prices), R/S is undefined
    if np.all(log_returns == 0.0):
        return None

    # Collect (log_lag, log_rs) pairs for OLS regression
    log_lags: list[float] = []
    log_rs_values: list[float] = []

    for lag in range(10, max_lag):
        # Number of non-overlapping windows
        n_windows: int = len(log_returns) // lag
        if n_windows < 1:
            continue

        rs_sum: float = 0.0
        valid_windows: int = 0

        for i in range(n_windows):
            window: np.ndarray = log_returns[i * lag : (i + 1) * lag]
            window_std: float = float(np.std(window, ddof=0))

            # Skip windows with zero std (constant returns in window)
            if window_std == 0.0 or not math.isfinite(window_std):
                continue

            # Cumulative deviations from window mean
            window_mean: float = float(np.mean(window))
            cumulative_dev: np.ndarray = np.cumsum(window - window_mean)

            # Rescaled range: (max - min) of cumulative deviations / std
            r: float = float(np.max(cumulative_dev) - np.min(cumulative_dev))
            rs: float = r / window_std

            if not math.isfinite(rs):
                continue

            rs_sum += rs
            valid_windows += 1

        if valid_windows == 0:
            continue

        mean_rs: float = rs_sum / valid_windows

        if mean_rs <= 0.0 or not math.isfinite(mean_rs):
            continue

        log_lags.append(math.log(lag))
        log_rs_values.append(math.log(mean_rs))

    # Need at least 2 points for OLS regression
    if len(log_lags) < 2:
        return None

    # OLS regression: log(R/S) = H * log(lag) + intercept
    x: np.ndarray = np.array(log_lags, dtype=float)
    y: np.ndarray = np.array(log_rs_values, dtype=float)

    x_mean: float = float(np.mean(x))
    y_mean: float = float(np.mean(y))

    ss_xx: float = float(np.sum((x - x_mean) ** 2))
    ss_xy: float = float(np.sum((x - x_mean) * (y - y_mean)))
    ss_yy: float = float(np.sum((y - y_mean) ** 2))

    # Guard: zero variance in x (all lags identical — shouldn't happen)
    if ss_xx == 0.0:
        return None

    slope: float = ss_xy / ss_xx

    # R-squared: coefficient of determination
    ss_res: float = float(np.sum((y - (slope * x + (y_mean - slope * x_mean))) ** 2))

    if ss_yy == 0.0:
        # All y values identical — degenerate case
        return None

    r_squared: float = 1.0 - ss_res / ss_yy

    if not math.isfinite(r_squared) or r_squared < r_squared_threshold:
        return None

    if not math.isfinite(slope):
        return None

    # Clamp to [0.0, 1.0]
    h: float = max(0.0, min(1.0, slope))
    return h
