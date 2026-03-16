"""Historical volatility estimator: Yang-Zhang.

Yang-Zhang is the sole OHLC historical volatility estimator. It mathematically
subsumes Parkinson (range-based) and Rogers-Satchell (drift-aware) by combining
overnight variance, close-to-open variance, and Rogers-Satchell variance.

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


def compute_hv_yang_zhang(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
) -> float | None:
    """Yang-Zhang (2000) historical volatility estimator.

    Combines overnight (open-to-previous-close) variance, close-to-open
    (intraday) variance, and Rogers-Satchell variance. Handles both drift
    and opening jumps. Minimum variance estimator independent of drift.

    Formula:
        sigma^2_yz = sigma^2_overnight + sigma^2_close + k * sigma^2_rs
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

    # Close-to-open (intraday) returns: ln(close_t / open_t)
    # Per Yang & Zhang (2000) Eq. 6-9, sigma^2_c uses close-to-open, NOT close-to-close.
    close_returns: np.ndarray = np.log(c[1:] / o[1:])

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

    # Combined Yang-Zhang variance: sigma^2_o + sigma^2_c + k * sigma^2_rs
    # Per Yang & Zhang (2000) Eq. 12: overnight and close-to-open get weight 1,
    # Rogers-Satchell gets weight k.
    variance: float = sigma2_overnight + sigma2_close + k * sigma2_rs

    if not math.isfinite(variance) or variance < 0.0:
        return None

    annualized: float = math.sqrt(variance * _TRADING_DAYS)
    return annualized if math.isfinite(annualized) else None
