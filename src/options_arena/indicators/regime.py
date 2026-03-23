"""Regime and macro indicator functions.

Three indicator functions for relative strength, correlation regime shifts,
and volume profile skew.

All functions take float/Series in, return float | None out.
No API calls. No Pydantic models. Pure math.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned


def compute_rs_vs_spx(
    ticker_returns: pd.Series,
    spx_returns: pd.Series,
    period: int = 60,
) -> float | None:
    """Relative strength vs SPX: cumulative return ratio over period.

    Computes the ratio of ticker cumulative return to SPX cumulative return
    over the trailing ``period`` trading days. A value > 1.0 means the ticker
    outperformed SPX.

    Args:
        ticker_returns: Daily returns for the ticker.
        spx_returns: Daily returns for SPX (^GSPC).
        period: Lookback period in trading days. Default 60.

    Returns:
        Relative strength ratio, or None if insufficient data.

    Raises:
        ValueError: If Series have mismatched lengths.
    """
    validate_aligned(ticker_returns, spx_returns)

    if len(ticker_returns) < period:
        return None

    ticker_tail = ticker_returns.iloc[-period:]
    spx_tail = spx_returns.iloc[-period:]

    ticker_prod = float(np.nanprod(1.0 + ticker_tail.to_numpy()))
    spx_prod = float(np.nanprod(1.0 + spx_tail.to_numpy()))
    ticker_cum = ticker_prod - 1.0
    spx_cum = spx_prod - 1.0

    if not math.isfinite(ticker_cum) or not math.isfinite(spx_cum):
        return None

    # Guard division by zero: if SPX had exactly 0 cumulative return
    denominator = 1.0 + spx_cum
    if denominator == 0.0:
        return None

    return (1.0 + ticker_cum) / denominator


def compute_correlation_regime_shift(
    ticker_returns: pd.Series,
    spx_returns: pd.Series,
    short_window: int = 20,
    long_window: int = 60,
) -> float | None:
    """Correlation regime shift: short-window minus long-window correlation.

    Positive = correlation increasing (regime shift toward risk-off / beta convergence).
    Negative = correlation decreasing (decoupling from market).

    Args:
        ticker_returns: Daily returns for the ticker.
        spx_returns: Daily returns for SPX (^GSPC).
        short_window: Short rolling window for correlation. Default 20.
        long_window: Long rolling window for correlation. Default 60.

    Returns:
        Correlation shift, or None if insufficient data.

    Raises:
        ValueError: If Series have mismatched lengths.
    """
    validate_aligned(ticker_returns, spx_returns)

    if len(ticker_returns) < long_window:
        return None

    short_corr = ticker_returns.rolling(short_window).corr(spx_returns).iloc[-1]
    long_corr = ticker_returns.rolling(long_window).corr(spx_returns).iloc[-1]

    short_val = float(short_corr)
    long_val = float(long_corr)

    if not math.isfinite(short_val) or not math.isfinite(long_val):
        return None

    return short_val - long_val


def compute_volume_profile_skew(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> float | None:
    """Volume profile skew: volume-weighted price vs simple average price.

    Positive = more volume at higher prices (bullish accumulation).
    Negative = more volume at lower prices (bearish distribution).

    Formula:
        vwap = sum(close * volume) / sum(volume)  (over trailing period)
        simple_avg = mean(close)  (over trailing period)
        skew = (vwap - simple_avg) / simple_avg

    Args:
        close: Daily closing prices.
        volume: Daily volume.
        period: Lookback period in trading days. Default 20.

    Returns:
        Volume profile skew as a decimal fraction, or None if insufficient data.

    Raises:
        ValueError: If Series have mismatched lengths.
    """
    validate_aligned(close, volume)

    if len(close) < period:
        return None

    close_tail = close.iloc[-period:]
    vol_tail = volume.iloc[-period:]

    total_volume = float(vol_tail.sum())
    if total_volume == 0.0:
        return None

    vwap = float(np.nansum(close_tail.to_numpy() * vol_tail.to_numpy())) / total_volume
    simple_avg = float(close_tail.mean())

    if not math.isfinite(vwap) or not math.isfinite(simple_avg):
        return None
    if simple_avg == 0.0:
        return None

    return (vwap - simple_avg) / simple_avg
