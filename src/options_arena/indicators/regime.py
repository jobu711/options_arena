"""Regime and macro indicator functions.

Seven indicator functions for market regime classification, VIX term structure,
risk-on/off scoring, sector momentum, relative strength, correlation regime
shifts, and volume profile skew.

All functions take float/Series in, return float | MarketRegime | None out.
No API calls. No Pydantic models. Pure math.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned
from options_arena.models.enums import MarketRegime


def classify_market_regime(
    vix: float,
    vix_sma_20: float,
    spx_returns_20d: float,
    spx_sma_slope: float,
) -> MarketRegime:
    """Classify market regime based on VIX and SPX metrics.

    Classification logic:
        CRISIS     — VIX >= 35 (extreme fear)
        VOLATILE   — VIX > vix_sma_20 * 1.2 (elevated vs recent avg)
        TRENDING   — |spx_returns_20d| > 3% AND spx_sma_slope has same sign
        MEAN_REVERTING — default (range-bound market)

    Args:
        vix: Current VIX level.
        vix_sma_20: 20-day simple moving average of VIX.
        spx_returns_20d: SPX cumulative return over 20 trading days (decimal, e.g. 0.05 = 5%).
        spx_sma_slope: Slope of SPX 20-day SMA (positive = uptrend).

    Returns:
        MarketRegime enum value.
    """
    # Guard against NaN/Inf — fall through to MEAN_REVERTING would be silent & wrong
    if (
        not math.isfinite(vix)
        or not math.isfinite(vix_sma_20)
        or not math.isfinite(spx_returns_20d)
        or not math.isfinite(spx_sma_slope)
    ):
        return MarketRegime.MEAN_REVERTING

    # Crisis: extreme VIX
    if vix >= 35.0:
        return MarketRegime.CRISIS

    # Volatile: VIX significantly above its recent average
    if vix_sma_20 > 0.0 and vix > vix_sma_20 * 1.2:
        return MarketRegime.VOLATILE

    # Trending: strong directional SPX move confirmed by SMA slope
    # Check magnitude + sign agreement: both positive or both negative
    if abs(spx_returns_20d) > 0.03 and (
        (spx_returns_20d > 0 and spx_sma_slope > 0) or (spx_returns_20d < 0 and spx_sma_slope < 0)
    ):
        return MarketRegime.TRENDING

    # Default: mean-reverting / range-bound
    return MarketRegime.MEAN_REVERTING


def compute_vix_term_structure(
    vix: float,
    vix3m: float | None,
) -> float | None:
    """VIX term structure: (VIX3M - VIX) / VIX.

    Positive values indicate contango (normal market — longer-dated vol > short-dated).
    Negative values indicate backwardation (fear — near-term vol > longer-dated).

    When VIX3M is unavailable, returns None (caller should use absolute VIX thresholds).

    Args:
        vix: Current VIX level (spot).
        vix3m: 3-month VIX level, or None if unavailable.

    Returns:
        Term structure ratio, or None if VIX3M unavailable or VIX is zero.
    """
    if vix3m is None:
        return None
    if not math.isfinite(vix) or not math.isfinite(vix3m):
        return None
    if vix == 0.0:
        return None
    return (vix3m - vix) / vix


def compute_risk_on_off(
    hyg_return: float | None,
    lqd_return: float | None,
) -> float | None:
    """Risk-on/off score: HYG 20-day return minus LQD 20-day return.

    Positive = risk-on (high yield outperforming investment grade, credit expansion).
    Negative = risk-off (flight to quality, credit contraction).

    Args:
        hyg_return: 20-day cumulative return of HYG (high yield corporate bonds).
        lqd_return: 20-day cumulative return of LQD (investment grade corporate bonds).

    Returns:
        Risk-on/off spread, or None if either input is unavailable.
    """
    if hyg_return is None or lqd_return is None:
        return None
    if not math.isfinite(hyg_return) or not math.isfinite(lqd_return):
        return None
    return hyg_return - lqd_return


def compute_sector_momentum(
    sector_etf_return: float | None,
    spx_return: float,
) -> float | None:
    """Sector relative momentum: sector ETF 20-day return minus SPX 20-day return.

    Positive = sector outperforming the broad market.
    Negative = sector underperforming the broad market.

    Args:
        sector_etf_return: 20-day cumulative return of the sector ETF.
        spx_return: 20-day cumulative return of SPX (^GSPC).

    Returns:
        Relative momentum, or None if sector ETF return is unavailable.
    """
    if sector_etf_return is None:
        return None
    if not math.isfinite(sector_etf_return) or not math.isfinite(spx_return):
        return None
    return sector_etf_return - spx_return


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
