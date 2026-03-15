"""Greeks aggregation for multi-leg option spreads.

Combines per-leg Greeks across a multi-leg spread with sign conventions:
- LONG legs: add Greeks as-is.
- SHORT legs: negate all Greeks (delta, gamma, theta, vega, rho).
- Quantity multiplier: multiply each Greek by ``leg.quantity``.

Returns ``OptionGreeks`` or ``None`` if any leg is missing Greeks.

This module only imports from ``models/`` — no API calls, no data fetching,
no pandas, no pricing engines (bsm, american).
"""

from __future__ import annotations

import logging
import math

from options_arena.models.enums import PositionSide
from options_arena.models.options import OptionGreeks, SpreadLeg

logger = logging.getLogger(__name__)


def aggregate_spread_greeks(legs: list[SpreadLeg]) -> OptionGreeks | None:
    """Aggregate Greeks across spread legs with sign convention.

    LONG legs: add Greeks as-is.
    SHORT legs: negate all Greeks (delta, gamma, theta, vega, rho).
    Quantity multiplier: multiply each Greek by ``leg.quantity``.

    Second-order Greeks (vanna, charm, vomma) are aggregated only when ALL
    legs have them populated (not ``None``). If any leg is missing any
    second-order Greek, all three are set to ``None`` on the result.

    The ``pricing_model`` on the result is taken from the first leg's
    ``contract.greeks.pricing_model``.

    If aggregate delta falls outside ``[-1, 1]``, it is clamped with a
    log warning.

    Args:
        legs: List of spread legs to aggregate. Must not be empty.

    Returns:
        Aggregated ``OptionGreeks``, or ``None`` if *legs* is empty or
        any leg has ``contract.greeks is None``.
    """
    if not legs:
        return None

    # Validate all legs have Greeks before aggregating
    for leg in legs:
        if leg.contract.greeks is None:
            return None

    # At this point we know every leg has non-None greeks
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta: float = 0.0
    total_vega: float = 0.0
    total_rho: float = 0.0

    # Track second-order availability
    all_second_order_present: bool = True
    total_vanna: float = 0.0
    total_charm: float = 0.0
    total_vomma: float = 0.0

    for leg in legs:
        greeks = leg.contract.greeks
        assert greeks is not None  # guaranteed by check above  # noqa: S101

        sign: float = 1.0 if leg.side == PositionSide.LONG else -1.0
        qty: float = float(leg.quantity)
        multiplier: float = sign * qty

        total_delta += multiplier * greeks.delta
        total_gamma += multiplier * greeks.gamma
        total_theta += multiplier * greeks.theta
        total_vega += multiplier * greeks.vega
        total_rho += multiplier * greeks.rho

        # Second-order Greeks
        if greeks.vanna is not None and greeks.charm is not None and greeks.vomma is not None:
            total_vanna += multiplier * greeks.vanna
            total_charm += multiplier * greeks.charm
            total_vomma += multiplier * greeks.vomma
        else:
            all_second_order_present = False

    # Clamp delta to [-1, 1] with warning
    if math.isfinite(total_delta) and not -1.0 <= total_delta <= 1.0:
        logger.warning(
            "Aggregate spread delta %.4f outside [-1, 1], clamping",
            total_delta,
        )
        total_delta = max(-1.0, min(1.0, total_delta))

    # Determine second-order values
    result_vanna: float | None = total_vanna if all_second_order_present else None
    result_charm: float | None = total_charm if all_second_order_present else None
    result_vomma: float | None = total_vomma if all_second_order_present else None

    # Use first leg's pricing model
    first_greeks = legs[0].contract.greeks
    assert first_greeks is not None  # noqa: S101
    pricing_model = first_greeks.pricing_model

    # Guard non-finite values before model_construct (which bypasses validators)
    primary_greeks = [total_delta, total_gamma, total_theta, total_vega, total_rho]
    if not all(math.isfinite(v) for v in primary_greeks):
        logger.warning("Non-finite aggregate Greeks detected, returning None")
        return None

    # Use model_construct to bypass validators — aggregate Greeks for spreads
    # can legitimately have negative gamma/vega (short-heavy spreads) which
    # would fail the single-contract validators.
    return OptionGreeks.model_construct(
        delta=total_delta,
        gamma=total_gamma,
        theta=total_theta,
        vega=total_vega,
        rho=total_rho,
        pricing_model=pricing_model,
        vanna=result_vanna,
        charm=result_charm,
        vomma=result_vomma,
    )
