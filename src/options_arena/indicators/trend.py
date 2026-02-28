"""Trend indicators: Rate of Change, ADX, Supertrend, and trend extensions.

All functions take pandas Series in, return pandas Series or float | None out.
NaN for warmup period — never filled or dropped.
"""

from __future__ import annotations

import math

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


# ---------------------------------------------------------------------------
# Trend extension functions (Issue #152)
# ---------------------------------------------------------------------------


def compute_multi_tf_alignment(
    daily_supertrend: pd.Series,
    weekly_close: pd.Series,
    weekly_period: int = 10,
    weekly_multiplier: float = 3.0,
) -> float | None:
    """Multi-timeframe alignment: daily supertrend direction + weekly supertrend agreement.

    Computes a weekly supertrend from ``weekly_close`` and compares the latest
    daily and weekly trend directions.

    Returns:
        1.0  — both daily and weekly bullish (aligned uptrend).
        -1.0 — both daily and weekly bearish (aligned downtrend).
        0.0  — conflicting signals.
        None — insufficient data or NaN at the latest bar.

    Args:
        daily_supertrend: Daily supertrend series (values +1 or -1, NaN for warmup).
        weekly_close: Weekly closing prices (for computing weekly supertrend).
        weekly_period: Supertrend period for weekly timeframe. Default 10.
        weekly_multiplier: Supertrend multiplier for weekly timeframe. Default 3.0.
    """
    if daily_supertrend.empty or weekly_close.empty:
        return None

    # Latest daily trend
    daily_latest = float(daily_supertrend.iloc[-1])
    if not math.isfinite(daily_latest):
        return None

    # Compute a simple weekly supertrend from close only (approximate: uses close as
    # proxy for high/low since we only have weekly close).  This is an approximation
    # but sufficient for alignment scoring.
    if len(weekly_close) < weekly_period + 1:
        return None

    # Use close as proxy for high/low to compute ATR-like measure (range = 0, so
    # use rolling std * multiplier as a band width proxy)
    rolling_std = weekly_close.rolling(weekly_period).std(ddof=0)
    hl2 = weekly_close
    upper_band = hl2 + weekly_multiplier * rolling_std
    lower_band = hl2 - weekly_multiplier * rolling_std

    # Iterative weekly trend determination
    n = len(weekly_close)
    close_arr = weekly_close.to_numpy(dtype=float)
    upper_arr = upper_band.to_numpy(dtype=float)
    lower_arr = lower_band.to_numpy(dtype=float)

    weekly_trend = np.empty(n)
    weekly_trend[:] = np.nan

    # Find first valid index (after warmup)
    first_valid = weekly_period
    if first_valid >= n:
        return None

    weekly_trend[first_valid] = 1.0  # start with uptrend

    for i in range(first_valid + 1, n):
        if np.isnan(upper_arr[i]) or np.isnan(lower_arr[i]):
            weekly_trend[i] = weekly_trend[i - 1]
            continue
        if weekly_trend[i - 1] == 1.0:
            if close_arr[i] < lower_arr[i]:
                weekly_trend[i] = -1.0
            else:
                weekly_trend[i] = 1.0
        else:
            if close_arr[i] > upper_arr[i]:
                weekly_trend[i] = 1.0
            else:
                weekly_trend[i] = -1.0

    weekly_latest = weekly_trend[-1]
    if not math.isfinite(weekly_latest):
        return None

    # Alignment
    if daily_latest > 0 and weekly_latest > 0:
        return 1.0
    if daily_latest < 0 and weekly_latest < 0:
        return -1.0
    return 0.0


def compute_rsi_divergence(
    close: pd.Series,
    rsi: pd.Series,
    lookback: int = 14,
) -> float | None:
    """RSI divergence detector.

    Detects bullish and bearish divergences between price and RSI over the
    trailing ``lookback`` bars.

    Bullish divergence: price makes a lower low, RSI makes a higher low.
    Bearish divergence: price makes a higher high, RSI makes a lower high.

    Returns:
        1.0 — bullish divergence detected.
        -1.0 — bearish divergence detected.
        0.0 — no divergence.
        None — insufficient data.

    Args:
        close: Daily closing prices.
        rsi: RSI series (0-100 scale).
        lookback: Number of bars to look back for swing detection. Default 14.

    Raises:
        ValueError: If Series have mismatched lengths.
    """
    validate_aligned(close, rsi)

    if len(close) < lookback + 1:
        return None

    # Extract the lookback window
    close_window = close.iloc[-(lookback + 1) :]
    rsi_window = rsi.iloc[-(lookback + 1) :]

    # Drop NaN
    valid_mask = close_window.notna() & rsi_window.notna()
    close_clean = close_window[valid_mask]
    rsi_clean = rsi_window[valid_mask]

    if len(close_clean) < 3:
        return None

    # Compare first half min/max to second half min/max for swing detection
    mid = len(close_clean) // 2

    first_half_close = close_clean.iloc[:mid]
    second_half_close = close_clean.iloc[mid:]
    first_half_rsi = rsi_clean.iloc[:mid]
    second_half_rsi = rsi_clean.iloc[mid:]

    if first_half_close.empty or second_half_close.empty:
        return None

    # Bullish divergence: price lower low, RSI higher low
    price_low_1 = float(first_half_close.min())
    price_low_2 = float(second_half_close.min())
    rsi_low_1 = float(first_half_rsi.min())
    rsi_low_2 = float(second_half_rsi.min())

    if (
        math.isfinite(price_low_1)
        and math.isfinite(price_low_2)
        and math.isfinite(rsi_low_1)
        and math.isfinite(rsi_low_2)
        and price_low_2 < price_low_1
        and rsi_low_2 > rsi_low_1
    ):
        return 1.0

    # Bearish divergence: price higher high, RSI lower high
    price_high_1 = float(first_half_close.max())
    price_high_2 = float(second_half_close.max())
    rsi_high_1 = float(first_half_rsi.max())
    rsi_high_2 = float(second_half_rsi.max())

    if (
        math.isfinite(price_high_1)
        and math.isfinite(price_high_2)
        and math.isfinite(rsi_high_1)
        and math.isfinite(rsi_high_2)
        and price_high_2 > price_high_1
        and rsi_high_2 < rsi_high_1
    ):
        return -1.0

    return 0.0


def compute_adx_exhaustion(
    adx_series: pd.Series,
    threshold: float = 40.0,
) -> float | None:
    """ADX exhaustion signal.

    Detects when a strong trend (ADX above threshold) is showing signs of
    exhaustion (ADX declining). This typically precedes a trend reversal or
    consolidation.

    Returns:
        1.0 — ADX above threshold AND declining (trend exhaustion signal).
        0.0 — no exhaustion signal (ADX below threshold or still rising).
        None — insufficient data or NaN at the latest bars.

    Args:
        adx_series: ADX indicator series.
        threshold: ADX level above which the trend is considered strong. Default 40.0.
    """
    if len(adx_series) < 2:
        return None

    current = float(adx_series.iloc[-1])
    previous = float(adx_series.iloc[-2])

    if not math.isfinite(current) or not math.isfinite(previous):
        return None

    if current > threshold and current < previous:
        return 1.0
    return 0.0
