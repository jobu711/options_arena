"""Historical volatility estimators: Parkinson, Rogers-Satchell, Yang-Zhang.

Three range-based volatility estimators that use OHLC data for more efficient
volatility estimation than the standard close-to-close method.

Rules:
- Takes pandas Series inputs, returns float | None.
- NO Pydantic models, NO API calls — pure math on pre-fetched data.
- Division-by-zero: guard with zero/NaN checks on ratios.
- Return ``None`` on insufficient data, not NaN or 0.0.
- All results annualized with sqrt(252).
"""

import math

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned

# Trading days per year for annualization
_TRADING_DAYS: int = 252


def compute_hv_parkinson(
    high: pd.Series,
    low: pd.Series,
    period: int = 20,
) -> float | None:
    """Parkinson (1980) historical volatility estimator using high-low range.

    More efficient than close-to-close because it captures intraday range
    information. Assumes no drift and continuous trading (no overnight gaps).

    Formula:
        sigma^2 = (1 / (4 * n * ln(2))) * Sum[ln(H_i / L_i)]^2
        Annualized sigma = sqrt(sigma^2 * 252)

    Reference: Parkinson, M. (1980) "The Extreme Value Method for Estimating
    the Variance of the Rate of Return", Journal of Business, 53(1), 61-65.

    Args:
        high: Daily high prices. Requires at least ``period + 1`` data points.
        low: Daily low prices. Must have same length as ``high``.
        period: Lookback window (default 20 trading days).

    Returns:
        Annualized Parkinson volatility, or ``None`` if insufficient data
        or non-finite result.

    Raises:
        ValueError: If ``high`` and ``low`` have mismatched lengths.
    """
    validate_aligned(high, low)

    if len(high) < period + 1:
        return None

    # Use the last `period` bars
    h: np.ndarray = high.iloc[-period:].to_numpy(dtype=float)
    l: np.ndarray = low.iloc[-period:].to_numpy(dtype=float)  # noqa: E741

    # Guard: high and low must be positive for log
    if np.any(h <= 0.0) or np.any(l <= 0.0):
        return None

    # Guard: high must be >= low (allow equality for flat bars)
    if np.any(h < l):
        return None

    hl_ratio: np.ndarray = h / l
    # Guard: division-by-zero already excluded by l > 0 check above

    log_hl: np.ndarray = np.log(hl_ratio)
    n: int = period

    # Parkinson variance: (1 / (4 * n * ln(2))) * sum(ln(H/L)^2)
    variance: float = float(np.sum(log_hl**2)) / (4.0 * n * math.log(2.0))

    if not math.isfinite(variance) or variance < 0.0:
        return None

    annualized: float = math.sqrt(variance * _TRADING_DAYS)
    return annualized if math.isfinite(annualized) else None


def compute_hv_rogers_satchell(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> float | None:
    """Rogers-Satchell (1991) historical volatility estimator.

    Accounts for non-zero drift (trending markets), unlike Parkinson.
    Uses all four OHLC prices for maximum information extraction.

    Formula:
        sigma^2 = (1/n) * Sum[ln(H/C)*ln(H/O) + ln(L/C)*ln(L/O)]
        Annualized sigma = sqrt(sigma^2 * 252)

    Reference: Rogers, L.C.G. & Satchell, S.E. (1991) "Estimating Variance
    from High, Low and Closing Prices", Annals of Applied Probability, 1(4).

    Args:
        open_: Daily open prices.
        high: Daily high prices.
        low: Daily low prices.
        close: Daily close prices.
        period: Lookback window (default 20 trading days).

    Returns:
        Annualized Rogers-Satchell volatility, or ``None`` if insufficient data
        or non-finite result.

    Raises:
        ValueError: If input Series have mismatched lengths.
    """
    validate_aligned(open_, high, low, close)

    if len(open_) < period + 1:
        return None

    # Use the last `period` bars
    o: np.ndarray = open_.iloc[-period:].to_numpy(dtype=float)
    h: np.ndarray = high.iloc[-period:].to_numpy(dtype=float)
    l: np.ndarray = low.iloc[-period:].to_numpy(dtype=float)  # noqa: E741
    c: np.ndarray = close.iloc[-period:].to_numpy(dtype=float)

    # Guard: all prices must be positive for log
    if np.any(o <= 0.0) or np.any(h <= 0.0) or np.any(l <= 0.0) or np.any(c <= 0.0):
        return None

    log_hc: np.ndarray = np.log(h / c)
    log_ho: np.ndarray = np.log(h / o)
    log_lc: np.ndarray = np.log(l / c)
    log_lo: np.ndarray = np.log(l / o)

    n: int = period
    variance: float = float(np.sum(log_hc * log_ho + log_lc * log_lo)) / n

    if not math.isfinite(variance) or variance < 0.0:
        return None

    annualized: float = math.sqrt(variance * _TRADING_DAYS)
    return annualized if math.isfinite(annualized) else None


def compute_hv_yang_zhang(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> float | None:
    """Yang-Zhang (2000) historical volatility estimator.

    Combines overnight (open-to-close) variance, close-to-close variance,
    and Rogers-Satchell variance. Handles both drift and opening jumps.
    Minimum variance estimator that is independent of drift and opening gaps.

    Formula:
        sigma^2_yz = sigma^2_overnight + k * sigma^2_close + (1 - k) * sigma^2_rs
        k = 0.34 / (1.34 + (n + 1) / (n - 1))

    Reference: Yang, D. & Zhang, Q. (2000) "Drift-Independent Volatility
    Estimation Based on High, Low, Open, and Close Prices", Journal of
    Business, 73(3), 477-492.

    Args:
        open_: Daily open prices.
        high: Daily high prices.
        low: Daily low prices.
        close: Daily close prices.
        period: Lookback window (default 20 trading days). Must be >= 2.

    Returns:
        Annualized Yang-Zhang volatility, or ``None`` if insufficient data
        or non-finite result.

    Raises:
        ValueError: If input Series have mismatched lengths.
    """
    validate_aligned(open_, high, low, close)

    if period < 2:
        return None

    # Need period + 1 bars: period bars for OHLC + 1 prior close for overnight return
    if len(open_) < period + 1:
        return None

    # Extract arrays: we need previous close for overnight returns
    # Use last (period + 1) bars to get period overnight returns
    o: np.ndarray = open_.iloc[-(period + 1) :].to_numpy(dtype=float)
    h: np.ndarray = high.iloc[-(period + 1) :].to_numpy(dtype=float)
    l: np.ndarray = low.iloc[-(period + 1) :].to_numpy(dtype=float)  # noqa: E741
    c: np.ndarray = close.iloc[-(period + 1) :].to_numpy(dtype=float)

    # Guard: all prices must be positive for log
    if np.any(o <= 0.0) or np.any(h <= 0.0) or np.any(l <= 0.0) or np.any(c <= 0.0):
        return None

    n: int = period

    # Overnight returns: ln(open_t / close_{t-1})
    # We have (period+1) bars, so overnight returns are from index 1 to end
    overnight_returns: np.ndarray = np.log(o[1:] / c[:-1])

    # Close-to-close returns: ln(close_t / close_{t-1})
    close_returns: np.ndarray = np.log(c[1:] / c[:-1])

    # Overnight variance (sample variance, ddof=1)
    overnight_mean: float = float(np.mean(overnight_returns))
    sigma2_overnight: float = float(np.sum((overnight_returns - overnight_mean) ** 2) / (n - 1))

    # Close-to-close variance (sample variance, ddof=1)
    close_mean: float = float(np.mean(close_returns))
    sigma2_close: float = float(np.sum((close_returns - close_mean) ** 2) / (n - 1))

    # Rogers-Satchell variance (using the last `period` bars for OHLC)
    h_rs: np.ndarray = h[1:]
    l_rs: np.ndarray = l[1:]  # noqa: E741
    o_rs: np.ndarray = o[1:]
    c_rs: np.ndarray = c[1:]

    log_hc: np.ndarray = np.log(h_rs / c_rs)
    log_ho: np.ndarray = np.log(h_rs / o_rs)
    log_lc: np.ndarray = np.log(l_rs / c_rs)
    log_lo: np.ndarray = np.log(l_rs / o_rs)

    sigma2_rs: float = float(np.sum(log_hc * log_ho + log_lc * log_lo)) / n

    # Yang-Zhang mixing coefficient
    # k = 0.34 / (1.34 + (n+1)/(n-1))
    k: float = 0.34 / (1.34 + (n + 1) / (n - 1))

    # Combined Yang-Zhang variance
    variance: float = sigma2_overnight + k * sigma2_close + (1.0 - k) * sigma2_rs

    if not math.isfinite(variance) or variance < 0.0:
        return None

    annualized: float = math.sqrt(variance * _TRADING_DAYS)
    return annualized if math.isfinite(annualized) else None
