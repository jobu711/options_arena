"""Options-specific indicators: IV Rank, IV Percentile, Put/Call Ratios, Max Pain,
PoP, Optimal DTE, Spread Quality, Max Loss Ratio.

Functions for IV metrics take scalars; Put/Call ratios take ints;
Max Pain takes pandas Series; PoP uses scipy.stats.norm.
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from options_arena.models.enums import OptionType
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

    Guard div-by-zero: returns NaN if call_volume is 0 (ratio is undefined).
    """
    if call_volume == 0:
        return float("nan")
    return float(put_volume / call_volume)


def put_call_ratio_oi(put_oi: int, call_oi: int) -> float:
    """Put/Call ratio by open interest.

    Guard div-by-zero: returns NaN if call_oi is 0 (ratio is undefined).
    """
    if call_oi == 0:
        return float("nan")
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


def compute_pop(d2: float, option_type: OptionType) -> float | None:
    """Probability of Profit (PoP): N(d2) for calls, N(-d2) for puts.

    Uses the BSM d2 parameter which must be pre-computed by the caller.
    PoP estimates the probability that the option expires in-the-money.

    Args:
        d2: BSM d2 value (pre-computed from the pricing formula).
        option_type: CALL or PUT.

    Returns:
        PoP as float in [0, 1], or ``None`` if d2 is not finite.

    Reference:
        Black-Scholes-Merton (1973), d2 = d1 - sigma * sqrt(T).
    """
    if not np.isfinite(d2):
        return None

    match option_type:
        case OptionType.CALL:
            return float(norm.cdf(d2))
        case OptionType.PUT:
            return float(norm.cdf(-d2))


def compute_optimal_dte(theta: float, expected_value: float | None) -> float | None:
    """Theta-normalised expected value.

    Higher values indicate better risk/reward per unit of daily time decay.
    A position with high expected value but low theta is preferable.

    Args:
        theta: Daily theta (time decay), typically negative for long positions.
        expected_value: Expected value of the position. ``None`` if unavailable.

    Returns:
        Ratio as float, or ``None`` if theta is zero or expected_value is ``None``.
    """
    if expected_value is None:
        return None

    if theta == 0.0:
        return None

    # Use absolute theta so the ratio sign reflects expected_value direction
    abs_theta = abs(theta)
    return expected_value / abs_theta


def compute_spread_quality(chain: pd.DataFrame) -> float | None:
    """OI-weighted average bid-ask spread. Lower is better.

    Weights each contract's bid-ask spread by its open interest, giving
    more importance to actively traded strikes.

    Args:
        chain: DataFrame with ``bid``, ``ask``, and ``openInterest`` columns.

    Returns:
        Weighted average spread as float (>= 0), or ``None`` if insufficient data.
    """
    required_cols = {"bid", "ask", "openInterest"}
    if chain.empty or not required_cols.issubset(chain.columns):
        return None

    bid = chain["bid"].to_numpy(dtype=float)
    ask = chain["ask"].to_numpy(dtype=float)
    oi = chain["openInterest"].to_numpy(dtype=float)

    spreads = ask - bid
    total_oi = float(np.nansum(oi))

    if total_oi == 0.0:
        return None

    weighted_spread = float(np.nansum(spreads * oi)) / total_oi
    return weighted_spread


def compute_max_loss_ratio(
    contract_cost: float,
    account_risk_budget: float,
) -> float | None:
    """Max loss ratio: contract_cost / account_risk_budget.

    For long options, max loss is the premium paid. This ratio expresses
    that loss as a fraction of the account's risk budget. Lower is better.

    Args:
        contract_cost: Premium paid for the contract (must be > 0).
        account_risk_budget: Maximum acceptable loss per trade (must be > 0).

    Returns:
        Ratio as float (>= 0), or ``None`` if either input is non-positive.
    """
    if contract_cost <= 0.0 or account_risk_budget <= 0.0:
        return None

    return contract_cost / account_risk_budget
