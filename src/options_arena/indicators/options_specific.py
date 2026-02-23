"""Options-specific indicators: IV Rank, IV Percentile, Put/Call Ratios, Max Pain.

Functions for IV metrics take scalars; Put/Call ratios take ints;
Max Pain takes pandas Series.
"""

import numpy as np
import pandas as pd

from options_arena.utils.exceptions import InsufficientDataError


def iv_rank(current_iv: float, iv_high: float, iv_low: float) -> float:
    """IV Rank: (current - low) / (high - low) * 100.

    Returns 0-100. Guard: if high == low, return 50.

    Reference: tastytrade/tastyworks IV Rank definition.
    """
    if iv_high == iv_low:
        return 50.0
    return (current_iv - iv_low) / (iv_high - iv_low) * 100.0


def iv_percentile(
    iv_history: pd.Series,
    current_iv: float,
) -> float:
    """IV Percentile: % of days in history where IV was lower than current.

    Count-based, NOT the same formula as IV Rank.
    Result is 0-100.

    Reference: CBOE IV Percentile methodology.

    Raises:
        InsufficientDataError: If ``len(iv_history) < 1``.
    """
    if len(iv_history) < 1:
        raise InsufficientDataError("IV percentile requires at least 1 data point in history")
    clean = iv_history.dropna()
    if len(clean) < 1:
        raise InsufficientDataError("IV percentile requires at least 1 non-NaN data point")
    count_lower = int(np.sum(clean < current_iv))
    return float(count_lower / len(clean) * 100.0)


def put_call_ratio_volume(put_volume: int, call_volume: int) -> float:
    """Put/Call ratio by volume.

    Guard div-by-zero: returns 0.0 if call_volume is 0.
    """
    if call_volume == 0:
        return 0.0
    return float(put_volume / call_volume)


def put_call_ratio_oi(put_oi: int, call_oi: int) -> float:
    """Put/Call ratio by open interest.

    Guard div-by-zero: returns 0.0 if call_oi is 0.
    """
    if call_oi == 0:
        return 0.0
    return float(put_oi / call_oi)


def max_pain(
    strikes: pd.Series,
    call_oi: pd.Series,
    put_oi: pd.Series,
) -> float:
    """Max pain: strike where total ITM option value is minimized.

    For each candidate strike, sum:
      - ITM call pain: sum of (candidate - strike_i) * call_oi_i for all strikes_i < candidate
      - ITM put pain: sum of (strike_i - candidate) * put_oi_i for all strikes_i > candidate

    Return the strike with minimum total pain.

    Reference: Options market max pain theory.

    Raises:
        InsufficientDataError: If ``len(strikes) < 1``.
    """
    if len(strikes) < 1:
        raise InsufficientDataError("Max pain requires at least 1 strike")
    if not (len(strikes) == len(call_oi) == len(put_oi)):
        msg = (
            f"strikes, call_oi, and put_oi must have equal length, "
            f"got {len(strikes)}, {len(call_oi)}, {len(put_oi)}"
        )
        raise ValueError(msg)

    strikes_arr = strikes.to_numpy(dtype=float)
    call_oi_arr = call_oi.to_numpy(dtype=float)
    put_oi_arr = put_oi.to_numpy(dtype=float)

    min_pain = float("inf")
    best_strike = float(strikes_arr[0])

    for candidate in strikes_arr:
        # Call holders lose money when strike < candidate (calls are ITM)
        # For each call at strike_i where strike_i < candidate:
        #   call loss = (candidate - strike_i) * call_oi_i
        call_itm_mask = strikes_arr < candidate
        call_pain = float(
            np.nansum((candidate - strikes_arr[call_itm_mask]) * call_oi_arr[call_itm_mask])
        )

        # Put holders lose money when strike > candidate (puts are ITM)
        # For each put at strike_i where strike_i > candidate:
        #   put loss = (strike_i - candidate) * put_oi_i
        put_itm_mask = strikes_arr > candidate
        put_pain = float(
            np.nansum((strikes_arr[put_itm_mask] - candidate) * put_oi_arr[put_itm_mask])
        )

        total_pain = call_pain + put_pain
        if total_pain < min_pain:
            min_pain = total_pain
            best_strike = float(candidate)

    return best_strike
