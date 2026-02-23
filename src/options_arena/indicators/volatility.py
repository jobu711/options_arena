"""Volatility indicators: Bollinger Band Width, ATR%, Keltner Channel Width.

All functions take pandas Series in, return pandas Series out.
NaN for warmup period — never filled or dropped.
"""

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned
from options_arena.utils.exceptions import InsufficientDataError


def bb_width(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.Series:
    """Bollinger Band width: (upper - lower) / middle.

    Uses population stddev (ddof=0).
    Warmup: first ``period - 1`` values are NaN.

    Formula:
        middle = SMA(close, period)
        upper  = middle + num_std * stddev(close, period, ddof=0)
        lower  = middle - num_std * stddev(close, period, ddof=0)
        width  = (upper - lower) / middle

    Reference: John Bollinger, "Bollinger on Bollinger Bands" (2001).

    Raises:
        InsufficientDataError: If ``len(close) < period``.
    """
    if len(close) < period:
        raise InsufficientDataError(
            f"Bollinger Band width requires at least {period} data points, got {len(close)}"
        )

    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std(ddof=0)
    upper = middle + num_std * std
    lower = middle - num_std * std
    width: pd.Series = (upper - lower) / middle
    return width


def atr_percent(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """ATR as percentage of close price.

    True Range = max(high - low, |high - prev_close|, |low - prev_close|).
    Uses Wilder's smoothing: ``ewm(alpha=1/period, adjust=False)``.
    Warmup: first ``period`` values are NaN.

    Reference: Wilder (1978) "New Concepts in Technical Trading Systems".

    Raises:
        InsufficientDataError: If ``len(close) < period + 1``.
    """
    validate_aligned(high, low, close)
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"ATR% requires at least {period + 1} data points, got {len(close)}"
        )

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Wilder's smoothing: seed with SMA of first `period` true range values
    # (first TR is NaN because prev_close is NaN at index 0)
    atr = true_range.ewm(alpha=1.0 / period, adjust=False).mean()

    # Set warmup to NaN: first `period` values
    atr_result = atr.copy()
    atr_result.iloc[:period] = np.nan

    # Guard division by zero when close is 0
    result: pd.Series = (atr_result / close.replace(0.0, np.nan)) * 100
    return result


def keltner_width(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20,
    atr_mult: float = 2.0,
) -> pd.Series:
    """Keltner Channel width: (upper - lower) / middle.

    Middle = EMA(close, period). Upper/Lower = middle +/- atr_mult * ATR(period).
    EMA seeded with SMA of first ``period`` values.
    Warmup: first ``period`` values are NaN.

    Reference: Chester Keltner (1960), modernized by Linda Raschke.

    Raises:
        InsufficientDataError: If ``len(close) < period + 1``.
    """
    validate_aligned(high, low, close)
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"Keltner width requires at least {period + 1} data points, got {len(close)}"
        )

    # EMA seeded with SMA of first `period` values (not first price)
    sma_seed = close.iloc[:period].mean()
    seeded = close.copy()
    seeded.iloc[:period] = np.nan
    seeded.iloc[period - 1] = sma_seed
    middle = seeded.ewm(span=period, adjust=False).mean()

    # ATR using Wilder's smoothing
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1.0 / period, adjust=False).mean()

    upper = middle + atr_mult * atr
    lower = middle - atr_mult * atr
    width = (upper - lower) / middle

    # Set warmup to NaN
    width_result = width.copy()
    width_result.iloc[:period] = np.nan
    result: pd.Series = width_result
    return result
