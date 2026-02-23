"""Oscillator indicators: RSI, Stochastic RSI, Williams %R.

All functions take pandas Series in, return pandas Series out.
NaN for warmup period — never filled or dropped.
"""

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned
from options_arena.utils.exceptions import InsufficientDataError


def rsi(
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing.

    Formula:
        RSI = 100 - (100 / (1 + RS))
        RS  = avg_gain / avg_loss (Wilder's smoothing)

    When avg_loss = 0: RSI = 100.
    Warmup: first ``period`` values are NaN.

    Reference: Wilder (1978) "New Concepts in Technical Trading Systems".

    Raises:
        InsufficientDataError: If ``len(close) < period + 1``.
    """
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"RSI requires at least {period + 1} data points, got {len(close)}"
        )

    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    # Wilder's smoothing: ewm(alpha=1/period, adjust=False)
    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()

    # Division-by-zero guard: when avg_loss = 0, RSI = 100
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_values = 100.0 - (100.0 / (1.0 + rs))
    # Only fill NaN caused by div-by-zero (where avg_loss was 0), not input NaN
    div_zero_mask = avg_loss.eq(0.0) & avg_gain.notna()
    rsi_values = rsi_values.copy()
    rsi_values[div_zero_mask] = 100.0

    # Set warmup to NaN
    rsi_result = rsi_values.copy()
    rsi_result.iloc[:period] = np.nan

    result: pd.Series = rsi_result
    return result


def stoch_rsi(
    close: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
) -> pd.Series:
    """Stochastic RSI: (RSI - RSI_low) / (RSI_high - RSI_low) * 100.

    When RSI range = 0: output = 50.
    Warmup: first ``rsi_period + stoch_period - 1`` values are NaN.

    Reference: Chande & Kroll (1994) "The New Technical Trader".

    Raises:
        InsufficientDataError: If ``len(close) < rsi_period + stoch_period``.
    """
    if len(close) < rsi_period + stoch_period:
        raise InsufficientDataError(
            f"Stochastic RSI requires at least {rsi_period + stoch_period} data points, "
            f"got {len(close)}"
        )

    rsi_values = rsi(close, period=rsi_period)

    rsi_low = rsi_values.rolling(window=stoch_period).min()
    rsi_high = rsi_values.rolling(window=stoch_period).max()

    rsi_range = rsi_high - rsi_low
    # Division-by-zero guard: when range = 0, output = 50
    stoch = ((rsi_values - rsi_low) / rsi_range.replace(0.0, np.nan)) * 100.0
    # Only fill NaN from div-by-zero (where range was 0 and rolling was valid)
    valid_mask = rsi_high.notna()
    div_zero_mask = valid_mask & rsi_range.eq(0.0)
    stoch = stoch.copy()
    stoch[div_zero_mask] = 50.0

    # Set warmup to NaN
    warmup = rsi_period + stoch_period - 1
    stoch_result = stoch.copy()
    stoch_result.iloc[:warmup] = np.nan

    result: pd.Series = stoch_result
    return result


def williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Williams %R: (highest_high - close) / (highest_high - lowest_low) * -100.

    Range: -100 to 0.
    When highest_high == lowest_low (flat data): output = -50.
    Warmup: first ``period - 1`` values are NaN.

    Reference: Larry Williams, "How I Made One Million Dollars".

    Raises:
        InsufficientDataError: If ``len(close) < period``.
    """
    validate_aligned(high, low, close)
    if len(close) < period:
        raise InsufficientDataError(
            f"Williams %R requires at least {period} data points, got {len(close)}"
        )

    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()

    hl_range = highest_high - lowest_low

    # Identify where the rolling window is valid (not warmup)
    valid_mask = highest_high.notna()

    # Division-by-zero guard: when range = 0, output = -50
    wr = ((highest_high - close) / hl_range.replace(0.0, np.nan)) * -100.0
    # Only fill NaN from div-by-zero (where range was 0), not input NaN
    div_zero_mask = valid_mask & hl_range.eq(0.0)
    wr = wr.copy()
    wr[div_zero_mask] = -50.0

    # Warmup NaN from rolling is preserved
    result: pd.Series = wr
    return result
