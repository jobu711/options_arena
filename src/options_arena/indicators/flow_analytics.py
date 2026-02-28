"""Options flow analytics: GEX, OI concentration, unusual activity, max pain magnet,
dollar volume trend.

Functions for options flow analysis take pandas DataFrames/Series in, return
``float | None`` out. No Pydantic models, no API calls. Pure math.
"""

import math

import numpy as np
import pandas as pd

from options_arena.indicators._validation import validate_aligned


def compute_gex(
    chain_calls: pd.DataFrame,
    chain_puts: pd.DataFrame,
    spot: float,
) -> float | None:
    """Net Gamma Exposure (GEX).

    GEX = sum(call_OI * call_gamma * 100 * spot) - sum(put_OI * put_gamma * 100 * spot)
    for strikes within +/- 10% of spot price.

    Positive GEX implies dealer long gamma (stabilising); negative implies dealer
    short gamma (amplifying moves).

    Args:
        chain_calls: DataFrame with ``openInterest`` and ``gamma`` columns.
        chain_puts: DataFrame with ``openInterest`` and ``gamma`` columns.
        spot: Current underlying price.

    Returns:
        Net GEX as float, or ``None`` if insufficient data.
    """
    if not math.isfinite(spot) or spot <= 0.0:
        return None

    required_cols = {"openInterest", "gamma"}
    if (
        chain_calls.empty
        or chain_puts.empty
        or not required_cols.issubset(chain_calls.columns)
        or not required_cols.issubset(chain_puts.columns)
    ):
        return None

    # Filter to ATM +/- 10 strikes for performance
    if "strike" in chain_calls.columns:
        calls = chain_calls[
            (chain_calls["strike"] >= spot * 0.9) & (chain_calls["strike"] <= spot * 1.1)
        ].copy()
    else:
        calls = chain_calls.copy()

    if "strike" in chain_puts.columns:
        puts = chain_puts[
            (chain_puts["strike"] >= spot * 0.9) & (chain_puts["strike"] <= spot * 1.1)
        ].copy()
    else:
        puts = chain_puts.copy()

    if calls.empty and puts.empty:
        return None

    call_gex = float(
        np.nansum(calls["openInterest"].to_numpy() * calls["gamma"].to_numpy() * 100.0 * spot)
    )
    put_gex = float(
        np.nansum(puts["openInterest"].to_numpy() * puts["gamma"].to_numpy() * 100.0 * spot)
    )

    result = call_gex - put_gex
    return result if math.isfinite(result) else None


def compute_oi_concentration(chain: pd.DataFrame) -> float | None:
    """OI concentration: max_strike_OI / total_OI.

    Higher values indicate more concentrated positioning at a single strike,
    which can act as a magnet or resistance level.

    Args:
        chain: DataFrame with ``openInterest`` column.

    Returns:
        Concentration ratio in [0, 1], or ``None`` if insufficient data.
    """
    if chain.empty or "openInterest" not in chain.columns:
        return None

    oi = chain["openInterest"].to_numpy(dtype=float)
    total_oi = float(np.nansum(oi))

    if total_oi == 0.0:
        return None

    max_oi = float(np.nanmax(oi))
    ratio = max_oi / total_oi
    return ratio if math.isfinite(ratio) else None


def compute_unusual_activity(chain: pd.DataFrame) -> float | None:
    """Unusual activity score: premium-weighted volume/OI for strikes where vol > 2x OI.

    Identifies smart-money or institutional flow by flagging strikes with
    unusually high volume relative to open interest. Weighting by premium
    (mid price) ensures high-value trades dominate the score.

    Args:
        chain: DataFrame with ``volume``, ``openInterest``, ``bid``, and ``ask`` columns.

    Returns:
        Unusual activity score as float (>= 0), or ``None`` if insufficient data.
    """
    required_cols = {"volume", "openInterest", "bid", "ask"}
    if chain.empty or not required_cols.issubset(chain.columns):
        return None

    vol = chain["volume"].to_numpy(dtype=float)
    oi = chain["openInterest"].to_numpy(dtype=float)
    bid = chain["bid"].to_numpy(dtype=float)
    ask = chain["ask"].to_numpy(dtype=float)
    mid = (bid + ask) / 2.0

    # Filter to unusual: volume > 2 * OI, and OI > 0 to avoid div-by-zero noise
    unusual_mask = (vol > 2.0 * oi) & (oi > 0)

    if not np.any(unusual_mask):
        return 0.0

    # Premium-weighted vol/OI ratio for unusual strikes
    # Guard against zero OI in the denominator (already filtered but be safe)
    safe_oi = np.where(oi[unusual_mask] == 0.0, np.nan, oi[unusual_mask])
    ratios = vol[unusual_mask] / safe_oi
    premiums = mid[unusual_mask]

    total_premium = float(np.nansum(premiums))
    if total_premium == 0.0:
        return 0.0

    weighted_score = float(np.nansum(ratios * premiums)) / total_premium
    return weighted_score


def compute_max_pain_magnet(spot: float, max_pain: float | None) -> float | None:
    """Max pain magnet strength: 1 - (|spot - max_pain| / spot).

    Closer to 1.0 means price is near max pain (stronger gravitational pull).
    Below 0.0 means spot is more than 100% away from max pain (extreme divergence).

    Args:
        spot: Current underlying price.
        max_pain: Max pain strike price, or ``None`` if not computed.

    Returns:
        Magnet strength as float, or ``None`` if max_pain is ``None`` or spot is zero.
    """
    if max_pain is None:
        return None

    if not math.isfinite(spot) or spot <= 0.0:
        return None
    if not math.isfinite(max_pain):
        return None

    distance = abs(spot - max_pain) / spot
    return 1.0 - distance


def compute_dollar_volume_trend(
    close: pd.Series,
    volume: pd.Series,
    period: int = 20,
) -> float | None:
    """20-day slope of dollar volume (close x volume).

    Positive slope indicates increasing institutional flow; negative indicates
    waning interest.

    Args:
        close: Series of closing prices.
        volume: Series of volume values.
        period: Lookback window for slope calculation (default 20).

    Returns:
        Slope of dollar volume (float), or ``None`` if insufficient data.
    """
    validate_aligned(close, volume)

    if len(close) < period:
        return None

    dollar_vol = close * volume
    recent = dollar_vol.iloc[-period:].to_numpy(dtype=float)

    # Drop NaN values
    mask = np.isfinite(recent)
    if np.sum(mask) < 2:
        return None

    clean = recent[mask]
    x = np.arange(len(clean), dtype=float)

    # Linear regression slope via least squares
    x_mean = np.mean(x)
    y_mean = np.mean(clean)
    denom = float(np.sum((x - x_mean) ** 2))

    if denom == 0.0:
        return 0.0

    slope = float(np.sum((x - x_mean) * (clean - y_mean))) / denom
    return slope if math.isfinite(slope) else None
