"""Moving average indicators: SMA Alignment, VWAP Deviation.

All functions take pandas Series in, return pandas Series out.
NaN for warmup period — never filled or dropped.
"""

import numpy as np
import pandas as pd

from options_arena.utils.exceptions import InsufficientDataError


def sma_alignment(
    close: pd.Series,
    short: int = 20,
    medium: int = 50,
    long: int = 200,
) -> pd.Series:
    """SMA convergence/alignment measure.

    Compute SMA(short), SMA(medium), SMA(long).
    Alignment = average of the short-vs-long and medium-vs-long distances,
    normalized by the long SMA (positive = bullish alignment).

    Formula:
        alignment = ((SMA_short - SMA_long) / SMA_long * 100
                   + (SMA_medium - SMA_long) / SMA_long * 100) / 2

    Warmup: first ``long - 1`` values are NaN.

    Raises:
        InsufficientDataError: If ``len(close) < long``.
    """
    if len(close) < long:
        raise InsufficientDataError(
            f"SMA alignment requires at least {long} data points, got {len(close)}"
        )

    sma_short = close.rolling(window=short).mean()
    sma_medium = close.rolling(window=medium).mean()
    sma_long = close.rolling(window=long).mean()

    # Guard division by zero when SMA_long is 0
    safe_long = sma_long.replace(0.0, np.nan)

    short_dist = (sma_short - sma_long) / safe_long * 100
    medium_dist = (sma_medium - sma_long) / safe_long * 100
    alignment: pd.Series = (short_dist + medium_dist) / 2
    return alignment


def vwap_deviation(
    close: pd.Series,
    volume: pd.Series,
) -> pd.Series:
    """Percentage deviation from cumulative VWAP.

    VWAP = cumsum(close * volume) / cumsum(volume).
    Result = (close - VWAP) / VWAP * 100.

    No warmup: all values are computed from the start.

    Raises:
        InsufficientDataError: If ``len(close) < 1``.
    """
    if len(close) < 1:
        raise InsufficientDataError("VWAP deviation requires at least 1 data point, got 0")

    cum_vol_price = (close * volume).cumsum()
    cum_vol = volume.cumsum()

    # Guard division by zero when cumulative volume is 0
    vwap = cum_vol_price / cum_vol.replace(0.0, np.nan)
    safe_vwap = vwap.replace(0.0, np.nan)
    deviation: pd.Series = (close - vwap) / safe_vwap * 100
    return deviation
