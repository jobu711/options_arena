"""Fundamental catalyst indicators.

Five indicator functions for earnings, short interest, dividend impact, and
IV crush history. All functions take float/Series in, return float | None out.
No API calls. No Pydantic models. Pure math.
"""

from __future__ import annotations

import math

import pandas as pd


def compute_earnings_em_ratio(
    expected_move: float | None,
    avg_post_earnings_move: float | None,
) -> float | None:
    """Earnings expected move ratio: IV-implied EM / avg actual post-earnings move.

    A ratio > 1 means the options market is overpricing the expected earnings
    move relative to historical actuals (IV premium). A ratio < 1 means the
    market is underpricing it.

    Args:
        expected_move: IV-implied expected move (e.g. from straddle pricing).
        avg_post_earnings_move: Historical average absolute post-earnings move.

    Returns:
        Ratio as float, or None if either input is missing or denominator is zero.
    """
    if expected_move is None or avg_post_earnings_move is None:
        return None
    if not math.isfinite(expected_move) or not math.isfinite(avg_post_earnings_move):
        return None
    if avg_post_earnings_move == 0.0:
        return None
    return expected_move / avg_post_earnings_move


def compute_earnings_impact(
    days_to_earnings: int | None,
    dte: int,
) -> float | None:
    """Days-to-earnings impact score.

    Higher score when earnings fall within the option's life (DTE window).
    Returns a 0-1 score based on proximity: closer earnings = higher impact.

    Formula:
        If earnings outside DTE window: 0.0
        Otherwise: 1.0 - (days_to_earnings / dte)

    Args:
        days_to_earnings: Days until next earnings announcement.
        dte: Days to expiration of the option contract.

    Returns:
        Impact score in [0.0, 1.0], or None if days_to_earnings is unavailable.
    """
    if days_to_earnings is None:
        return None
    if dte <= 0:
        return None
    if days_to_earnings < 0:
        # Earnings already passed
        return 0.0
    if days_to_earnings > dte:
        # Earnings outside option's life
        return 0.0
    return 1.0 - (days_to_earnings / dte)


def compute_short_interest(
    short_ratio: float | None,
) -> float | None:
    """Short interest ratio passthrough with validation.

    Passes through the yfinance ``info.shortRatio`` value after validating
    it is finite and non-negative.

    Args:
        short_ratio: Short ratio (days to cover) from yfinance. None if missing.

    Returns:
        The validated short ratio, or None when missing or invalid.
    """
    if short_ratio is None:
        return None
    if not math.isfinite(short_ratio):
        return None
    if short_ratio < 0.0:
        return None
    return short_ratio


def compute_div_impact(
    div_yield: float,
    dte: int,
    days_to_ex: int | None,
) -> float | None:
    """Dividend impact score.

    Higher score when the ex-dividend date falls within the option's DTE window.
    Factors in the dividend yield magnitude: larger yield = higher impact.

    Formula:
        If ex-date outside DTE window or unavailable: 0.0
        base_proximity = 1.0 - (days_to_ex / dte)
        impact = base_proximity * min(div_yield / 0.05, 1.0)
        (scaled so a 5% yield is maximum weight)

    Args:
        div_yield: Annual dividend yield as decimal fraction (e.g. 0.02 = 2%).
        dte: Days to expiration of the option contract.
        days_to_ex: Days until next ex-dividend date. None if unavailable.

    Returns:
        Impact score in [0.0, 1.0], or None if days_to_ex is unavailable.
    """
    if days_to_ex is None:
        return None
    if dte <= 0:
        return None
    if not math.isfinite(div_yield):
        return None
    if days_to_ex < 0 or days_to_ex > dte:
        return 0.0
    # Proximity: closer ex-date = higher base score
    base_proximity = 1.0 - (days_to_ex / dte)
    # Yield magnitude weight: 5% yield = full weight, capped at 1.0
    yield_weight = min(div_yield / 0.05, 1.0) if div_yield > 0.0 else 0.0
    return base_proximity * yield_weight


def compute_iv_crush_history(
    hv_pre_earnings: pd.Series | None,
    hv_post_earnings: pd.Series | None,
) -> float | None:
    """IV crush proxy using historical volatility before vs after earnings.

    Since yfinance provides no historical IV data, we use realized (historical)
    volatility as a proxy. The ratio of pre-earnings HV to post-earnings HV
    indicates the typical volatility contraction around earnings.

    Formula:
        ratio = mean(hv_pre_earnings) / mean(hv_post_earnings)
        A ratio > 1 means volatility typically contracts after earnings (IV crush).
        A ratio < 1 means volatility typically expands after earnings.

    Args:
        hv_pre_earnings: Historical volatility values in the window before earnings.
        hv_post_earnings: Historical volatility values in the window after earnings.

    Returns:
        HV crush ratio, or None if either input is missing or insufficient.
    """
    if hv_pre_earnings is None or hv_post_earnings is None:
        return None
    if hv_pre_earnings.empty or hv_post_earnings.empty:
        return None

    pre_clean = hv_pre_earnings.dropna()
    post_clean = hv_post_earnings.dropna()

    if pre_clean.empty or post_clean.empty:
        return None

    pre_mean = float(pre_clean.mean())
    post_mean = float(post_clean.mean())

    if not math.isfinite(pre_mean) or not math.isfinite(post_mean):
        return None
    if post_mean == 0.0:
        return None

    return pre_mean / post_mean
