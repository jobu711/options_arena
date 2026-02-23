"""Unified pricing dispatch by ExerciseStyle.

Routes ``option_price``, ``option_greeks``, and ``option_iv`` to the correct
pricing engine based on ``ExerciseStyle``:
  - AMERICAN -> BAW (``american.py``)
  - EUROPEAN -> BSM (``bsm.py``)

This is a pure routing layer — no business logic, no data fetching, no pandas.
"""

import logging

from options_arena.models.config import PricingConfig
from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.models.options import OptionGreeks
from options_arena.pricing.american import american_greeks, american_iv, american_price
from options_arena.pricing.bsm import bsm_greeks, bsm_iv, bsm_price

logger = logging.getLogger(__name__)


def option_price(
    exercise_style: ExerciseStyle,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> float:
    """Compute option price by dispatching to BSM or BAW based on exercise style.

    Args:
        exercise_style: AMERICAN dispatches to BAW, EUROPEAN to BSM.
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: CALL or PUT.

    Returns:
        Option price as float.
    """
    match exercise_style:
        case ExerciseStyle.AMERICAN:
            return american_price(S, K, T, r, q, sigma, option_type)
        case ExerciseStyle.EUROPEAN:
            return bsm_price(S, K, T, r, q, sigma, option_type)


def option_greeks(
    exercise_style: ExerciseStyle,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> OptionGreeks:
    """Compute option Greeks by dispatching to BSM or BAW based on exercise style.

    Args:
        exercise_style: AMERICAN dispatches to BAW, EUROPEAN to BSM.
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: CALL or PUT.

    Returns:
        OptionGreeks with pricing_model set to BAW or BSM.
    """
    match exercise_style:
        case ExerciseStyle.AMERICAN:
            return american_greeks(S, K, T, r, q, sigma, option_type)
        case ExerciseStyle.EUROPEAN:
            return bsm_greeks(S, K, T, r, q, sigma, option_type)


def option_iv(
    exercise_style: ExerciseStyle,
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    option_type: OptionType,
    config: PricingConfig | None = None,
) -> float:
    """Solve for implied volatility by dispatching to BSM or BAW based on exercise style.

    Args:
        exercise_style: AMERICAN dispatches to BAW (brentq), EUROPEAN to BSM (Newton-Raphson).
        market_price: Observed market price.
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        option_type: CALL or PUT.
        config: Solver configuration. Uses PricingConfig() defaults if None.

    Returns:
        Implied volatility as float.
    """
    if config is None:
        config = PricingConfig()
    match exercise_style:
        case ExerciseStyle.AMERICAN:
            return american_iv(market_price, S, K, T, r, q, option_type, config)
        case ExerciseStyle.EUROPEAN:
            return bsm_iv(market_price, S, K, T, r, q, option_type, config=config)
