"""IV smoothing via put-call parity spread weighting.

Provides ``smooth_iv_parity()`` which computes a liquidity-weighted average of
call and put implied volatilities using inverse bid-ask spread as the weighting
signal. Tighter spreads indicate more reliable IV estimates, so they receive
higher weight.

This is part of the volatility intelligence pipeline: when both call and put IVs
are available at the same strike, smoothing produces a more robust IV estimate
than using either side alone.

Internal module — consumers import from ``options_arena.pricing``.
"""

import logging
import math

logger = logging.getLogger(__name__)

# Minimum spread percentage to prevent division-by-zero in inverse-spread weights.
_MIN_SPREAD_PCT: float = 0.001

# IV ratio threshold for logging a warning (e.g., call_iv / put_iv > 2.0).
_IV_RATIO_WARNING_THRESHOLD: float = 2.0


def _is_valid_iv(iv: float) -> bool:
    """Check whether an IV value is valid (finite and strictly positive).

    Args:
        iv: Implied volatility value.

    Returns:
        True if ``iv`` is finite and > 0.
    """
    return math.isfinite(iv) and iv > 0.0


def _relative_spread(bid: float, ask: float) -> float:
    """Compute relative spread as ``(ask - bid) / mid``.

    Handles edge cases:
    - Zero bid: uses ``ask`` as the denominator (bid-less spread).
    - Both zero: returns NaN (degenerate case).
    - Stale bid > ask: clamps spread to 0 before computing relative.

    Args:
        bid: Bid price.
        ask: Ask price.

    Returns:
        Relative spread percentage, or NaN when both prices are zero.
    """
    raw_spread = max(0.0, ask - bid)
    mid = (ask + bid) / 2.0

    if mid > 0.0:
        return raw_spread / mid

    # Zero bid — fall back to ask as denominator.
    if ask > 0.0:
        return raw_spread / ask

    # Both zero — no usable spread information.
    return float("nan")


def smooth_iv_parity(
    call_iv: float,
    put_iv: float,
    call_bid: float,
    call_ask: float,
    put_bid: float,
    put_ask: float,
) -> float:
    """Compute a liquidity-weighted average of call and put implied volatilities.

    Uses inverse relative bid-ask spread as the weighting signal: the side with the
    tighter spread (more liquid, more reliable IV) receives higher weight.

    Algorithm:
      1. Validate both IVs (finite and positive). If only one valid, return it.
      2. If both invalid, return NaN.
      3. Compute relative spread for each side.
      4. If both spreads are zero or non-finite, return simple average.
      5. Weights = inverse spread (clamped to ``_MIN_SPREAD_PCT``).
      6. Normalize and return weighted average.

    Edge cases:
      - Zero bid: spread computed from ask only.
      - IV ratio > 2.0: logs a warning but still averages (does not discard).
      - One IV is 0 or NaN: treated as invalid, returns the valid side.

    Args:
        call_iv: Call implied volatility (annualized decimal, e.g. 0.30 = 30%).
        put_iv: Put implied volatility (annualized decimal).
        call_bid: Call option bid price.
        call_ask: Call option ask price.
        put_bid: Put option bid price.
        put_ask: Put option ask price.

    Returns:
        Smoothed IV as a float. NaN if both IVs are invalid.
    """
    call_valid = _is_valid_iv(call_iv)
    put_valid = _is_valid_iv(put_iv)

    # --- One or both invalid ---
    if call_valid and not put_valid:
        return call_iv
    if put_valid and not call_valid:
        return put_iv
    if not call_valid and not put_valid:
        return float("nan")

    # --- Both valid — log warning if wildly different ---
    iv_ratio = max(call_iv, put_iv) / min(call_iv, put_iv)
    if iv_ratio > _IV_RATIO_WARNING_THRESHOLD:
        logger.warning(
            "IV ratio %.2f exceeds %.1f threshold (call_iv=%.4f, put_iv=%.4f) "
            "— averaging despite large discrepancy",
            iv_ratio,
            _IV_RATIO_WARNING_THRESHOLD,
            call_iv,
            put_iv,
        )

    # --- Compute relative spreads ---
    call_spread_pct = _relative_spread(call_bid, call_ask)
    put_spread_pct = _relative_spread(put_bid, put_ask)

    call_spread_usable = math.isfinite(call_spread_pct)
    put_spread_usable = math.isfinite(put_spread_pct)

    # If both spreads are zero or non-finite, fall back to simple average.
    if not call_spread_usable and not put_spread_usable:
        return (call_iv + put_iv) / 2.0

    # If only one spread is usable, use simple average (we can't weight properly).
    if not call_spread_usable or not put_spread_usable:
        return (call_iv + put_iv) / 2.0

    # Both spreads zero (bid == ask on both sides) — simple average.
    if call_spread_pct == 0.0 and put_spread_pct == 0.0:
        return (call_iv + put_iv) / 2.0

    # --- Inverse-spread weighting ---
    w_call = 1.0 / max(call_spread_pct, _MIN_SPREAD_PCT)
    w_put = 1.0 / max(put_spread_pct, _MIN_SPREAD_PCT)

    total_weight = w_call + w_put
    return (w_call * call_iv + w_put * put_iv) / total_weight
