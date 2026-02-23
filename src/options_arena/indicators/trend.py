"""Trend indicators: Rate of Change, ADX, Supertrend.

All functions take pandas Series in, return pandas Series out.
NaN for warmup period — never filled or dropped.
"""

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned
from options_arena.utils.exceptions import InsufficientDataError


def roc(
    close: pd.Series,
    period: int = 12,
) -> pd.Series:
    """Rate of Change: (close - close_n_periods_ago) / close_n_periods_ago * 100.

    Warmup: first ``period`` values are NaN.

    Reference: StockCharts Technical Analysis documentation.

    Raises:
        InsufficientDataError: If ``len(close) < period + 1``.
    """
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"ROC requires at least {period + 1} data points, got {len(close)}"
        )

    prev_close = close.shift(period)
    # Guard division by zero when prev_close is 0
    result: pd.Series = (close - prev_close) / prev_close.replace(0.0, np.nan) * 100
    return result


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average Directional Index using Wilder's smoothing.

    Steps:
        1. Compute +DM and -DM from high/low differences.
        2. Smooth +DM, -DM, and TR using Wilder's smoothing.
        3. +DI = smoothed_+DM / smoothed_TR * 100.
        4. -DI = smoothed_-DM / smoothed_TR * 100.
        5. DX = |+DI - -DI| / (+DI + -DI) * 100.
        6. ADX = Wilder's smoothed DX.

    Warmup: first ``2 * period`` values are NaN (approximately).

    Reference: Wilder (1978) "New Concepts in Technical Trading Systems".

    Raises:
        InsufficientDataError: If ``len(close) < 2 * period + 1``.
    """
    validate_aligned(high, low, close)
    if len(close) < 2 * period + 1:
        raise InsufficientDataError(
            f"ADX requires at least {2 * period + 1} data points, got {len(close)}"
        )

    # +DM and -DM
    high_diff = high.diff()
    low_diff = -low.diff()  # Note: negative of diff because we want low[i-1] - low[i]

    plus_dm = pd.Series(
        np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0.0),
        index=close.index,
    )
    minus_dm = pd.Series(
        np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0.0),
        index=close.index,
    )

    # True Range
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing for +DM, -DM, TR
    alpha = 1.0 / period
    smoothed_tr = true_range.ewm(alpha=alpha, adjust=False).mean()
    smoothed_plus_dm = plus_dm.ewm(alpha=alpha, adjust=False).mean()
    smoothed_minus_dm = minus_dm.ewm(alpha=alpha, adjust=False).mean()

    # +DI and -DI
    safe_tr = smoothed_tr.replace(0.0, np.nan)
    plus_di = (smoothed_plus_dm / safe_tr) * 100.0
    minus_di = (smoothed_minus_dm / safe_tr) * 100.0

    # Only fill NaN from div-by-zero (where TR was 0), not genuine input NaN
    tr_zero_mask = smoothed_tr.eq(0.0) & smoothed_plus_dm.notna()
    plus_di = plus_di.copy()
    minus_di = minus_di.copy()
    plus_di[tr_zero_mask] = 0.0
    minus_di[tr_zero_mask] = 0.0

    # DX
    di_sum = plus_di + minus_di
    dx = (plus_di - minus_di).abs() / di_sum.replace(0.0, np.nan) * 100.0
    # Only fill NaN from div-by-zero (where di_sum was 0)
    di_sum_zero_mask = di_sum.eq(0.0) & plus_di.notna()
    dx = dx.copy()
    dx[di_sum_zero_mask] = 0.0

    # ADX = Wilder's smoothed DX
    adx_values = dx.ewm(alpha=alpha, adjust=False).mean()

    # Set warmup to NaN: first 2*period values
    adx_result = adx_values.copy()
    adx_result.iloc[: 2 * period] = np.nan

    result: pd.Series = adx_result
    return result


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.Series:
    """ATR-based Supertrend indicator.

    Returns +1 for uptrend, -1 for downtrend.

    Formula:
        basic_upper = (high + low) / 2 + multiplier * ATR(period)
        basic_lower = (high + low) / 2 - multiplier * ATR(period)
        Final bands are adjusted so they never move adversely.
        Trend flips when close crosses a band.

    Warmup: first ``period`` values are NaN.

    Reference: Olivier Seban, "Supertrend" indicator.

    Raises:
        InsufficientDataError: If ``len(close) < period + 1``.
    """
    validate_aligned(high, low, close)
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"Supertrend requires at least {period + 1} data points, got {len(close)}"
        )

    # Compute ATR using Wilder's smoothing
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1.0 / period, adjust=False).mean()

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    # Compute final bands iteratively (cannot be fully vectorized due to state)
    n = len(close)
    close_arr = close.to_numpy(dtype=float)
    upper_arr = basic_upper.to_numpy(dtype=float)
    lower_arr = basic_lower.to_numpy(dtype=float)

    final_upper = np.empty(n)
    final_lower = np.empty(n)
    trend = np.empty(n)

    final_upper[0] = upper_arr[0]
    final_lower[0] = lower_arr[0]
    trend[0] = 1.0  # start with uptrend

    for i in range(1, n):
        # Final upper band: never moves up (tightens down)
        if upper_arr[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1]:
            final_upper[i] = upper_arr[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final lower band: never moves down (tightens up)
        if lower_arr[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1]:
            final_lower[i] = lower_arr[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Determine trend
        if trend[i - 1] == 1.0:
            # Was uptrend
            if close_arr[i] < final_lower[i]:
                trend[i] = -1.0
            else:
                trend[i] = 1.0
        else:
            # Was downtrend
            if close_arr[i] > final_upper[i]:
                trend[i] = 1.0
            else:
                trend[i] = -1.0

    result = pd.Series(trend, index=close.index)
    # Set warmup to NaN
    result.iloc[:period] = np.nan

    typed_result: pd.Series = result
    return typed_result
