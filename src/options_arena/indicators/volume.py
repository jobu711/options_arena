"""Volume indicators: OBV Trend, Relative Volume, A/D Line Trend.

All functions take pandas Series in, return pandas Series out.
NaN for warmup period — never filled or dropped.
"""

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned
from options_arena.utils.exceptions import InsufficientDataError


def _rolling_slope(
    series: pd.Series,
    period: int,
) -> pd.Series:
    """Compute rolling linear regression slope over a window.

    Uses the least-squares formula with rolling sums (fully vectorized):
        slope = (n * sum(x*y) - sum(x) * sum(y)) / (n * sum(x^2) - sum(x)^2)
    where x = 0, 1, ..., n-1 for each window.

    Raises:
        ValueError: If ``period < 2`` (slope requires at least 2 points).
    """
    if period < 2:
        msg = f"Rolling slope requires period >= 2, got {period}"
        raise ValueError(msg)
    n = period
    x_sum = n * (n - 1) / 2.0
    x2_sum = n * (n - 1) * (2 * n - 1) / 6.0
    denom = n * x2_sum - x_sum * x_sum

    # sum(y) via rolling sum
    y_sum = series.rolling(window=n).sum()

    # sum(x*y): for window ending at index j, x_i = i for i=0..n-1
    # This equals sum_{k=j-n+1}^{j} (k - (j-n+1)) * series[k]
    # = sum(k * series[k]) - (j-n+1) * sum(series[k])
    # We compute sum(k * series[k]) via rolling sum of (index_weight * series)
    idx_weights = pd.Series(np.arange(len(series), dtype=float), index=series.index)
    weighted = idx_weights * series
    weighted_sum = weighted.rolling(window=n).sum()
    # Offset for each window: the starting index of the window = idx - n + 1
    window_start = idx_weights - (n - 1)
    xy_sum = weighted_sum - window_start * y_sum

    slope: pd.Series = (n * xy_sum - x_sum * y_sum) / denom
    return slope


def obv_trend(
    close: pd.Series,
    volume: pd.Series,
    slope_period: int = 20,
) -> pd.Series:
    """On-Balance Volume trend (slope of OBV via linear regression).

    OBV: cumulative sum of volume * sign(price change).
    Slope computed via rolling linear regression over slope_period.
    Warmup: first ``slope_period`` values are NaN (slope_period - 1 from rolling + 1 from diff).

    Reference: Joseph Granville, "New Key to Stock Market Profits" (1963).

    Raises:
        InsufficientDataError: If ``len(close) < slope_period + 1``.
    """
    validate_aligned(close, volume)
    if len(close) < slope_period + 1:
        raise InsufficientDataError(
            f"OBV trend requires at least {slope_period + 1} data points, got {len(close)}"
        )

    # sign of price change: +1 if up, -1 if down, 0 if unchanged
    price_sign = np.sign(close.diff())
    # First value has NaN from diff — set to 0 so OBV starts at 0
    price_sign = price_sign.copy()
    price_sign.iloc[0] = 0.0
    obv = (volume * price_sign).cumsum()

    result: pd.Series = _rolling_slope(obv, slope_period)
    return result


def relative_volume(
    volume: pd.Series,
    period: int = 20,
) -> pd.Series:
    """Current volume relative to its average over ``period`` days.

    Result = volume / SMA(volume, period).
    Warmup: first ``period - 1`` values are NaN.

    Raises:
        InsufficientDataError: If ``len(volume) < period``.
    """
    if len(volume) < period:
        raise InsufficientDataError(
            f"Relative volume requires at least {period} data points, got {len(volume)}"
        )

    avg_vol = volume.rolling(window=period).mean()
    # Guard division by zero (if average volume is 0)
    result: pd.Series = volume / avg_vol.replace(0.0, np.nan)
    return result


def ad_trend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    slope_period: int = 20,
) -> pd.Series:
    """Accumulation/Distribution line slope.

    CLV = ((close - low) - (high - close)) / (high - low).
    Guard div-by-zero: when high == low, CLV = 0.
    AD = cumsum(CLV * volume).
    Return rolling slope of AD line over slope_period.

    Reference: Marc Chaikin, "Chaikin Money Flow".

    Raises:
        InsufficientDataError: If ``len(close) < slope_period``.
    """
    validate_aligned(high, low, close, volume)
    if len(close) < slope_period:
        raise InsufficientDataError(
            f"A/D trend requires at least {slope_period} data points, got {len(close)}"
        )

    hl_range = high - low
    # CLV: guard division by zero — when high == low, CLV = 0
    clv = ((close - low) - (high - close)) / hl_range.replace(0.0, np.nan)
    flat_mask = hl_range.eq(0.0)
    clv = clv.copy()
    clv[flat_mask] = 0.0

    ad_line = (clv * volume).cumsum()

    result: pd.Series = _rolling_slope(ad_line, slope_period)
    return result
