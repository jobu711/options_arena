"""Shared helper functions for BSM and BAW pricing modules.

Internal module — not part of the public API. Consumers import from
``options_arena.pricing`` (dispatch layer), not from here.
"""

from options_arena.models.enums import OptionType, PricingModel
from options_arena.models.options import OptionGreeks


def validate_positive_inputs(S: float, K: float) -> None:
    """Validate that spot and strike prices are positive.

    Args:
        S: Spot price.
        K: Strike price.

    Raises:
        ValueError: If S <= 0 or K <= 0.
    """
    if S <= 0.0:
        raise ValueError(f"S (spot price) must be > 0, got {S}")
    if K <= 0.0:
        raise ValueError(f"K (strike price) must be > 0, got {K}")


def intrinsic_value(S: float, K: float, option_type: OptionType) -> float:
    """Return the intrinsic value of an option.

    Args:
        S: Spot price.
        K: Strike price.
        option_type: CALL or PUT.

    Returns:
        Intrinsic value, floored at 0.
    """
    match option_type:
        case OptionType.CALL:
            return max(S - K, 0.0)
        case OptionType.PUT:
            return max(K - S, 0.0)


def is_itm(S: float, K: float, option_type: OptionType) -> bool:
    """Check whether an option is in-the-money.

    Args:
        S: Spot price.
        K: Strike price.
        option_type: CALL or PUT.

    Returns:
        True if the option is in-the-money.
    """
    match option_type:
        case OptionType.CALL:
            return S > K
        case OptionType.PUT:
            return K > S


def boundary_greeks(
    S: float, K: float, option_type: OptionType, pricing_model: PricingModel
) -> OptionGreeks:
    """Return boundary Greeks when T <= 0 or sigma <= 0.

    At expiration or with zero volatility:
    - Delta = 1.0 (call ITM) or 0.0 (call OTM); -1.0 (put ITM) or 0.0 (put OTM).
    - Gamma, vega, rho, theta = 0.0.

    Args:
        S: Spot price.
        K: Strike price.
        option_type: CALL or PUT.
        pricing_model: BSM or BAW — set on the returned OptionGreeks.

    Returns:
        ``OptionGreeks`` with boundary values.
    """
    itm = is_itm(S, K, option_type)

    match option_type:
        case OptionType.CALL:
            delta = 1.0 if itm else 0.0
        case OptionType.PUT:
            delta = -1.0 if itm else 0.0

    return OptionGreeks(
        delta=delta,
        gamma=0.0,
        theta=0.0,
        vega=0.0,
        rho=0.0,
        pricing_model=pricing_model,
    )
