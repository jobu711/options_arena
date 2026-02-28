"""Second-order Greeks via central finite difference on existing pricing dispatch.

Computes vanna, charm, and vomma using the unified ``option_greeks`` dispatch layer.
These are cross-Greeks (mixed partial derivatives) that measure how first-order
Greeks change with respect to other variables:

- **Vanna**: d(delta)/d(sigma) — how delta changes with volatility.
- **Charm**: d(delta)/d(T) — how delta changes with time (delta decay).
- **Vomma**: d(vega)/d(sigma) — vega convexity.

All use centered finite differences for O(h^2) accuracy, falling back to forward
difference when the backward perturbation would produce invalid parameters.

Architecture:
- Imports from ``pricing/dispatch`` ONLY — never ``pricing/bsm`` or ``pricing/american``.
- Uses ``math`` for scalar operations — no numpy.
- Returns ``float`` (not ``None``) — these always produce a value given valid inputs.
"""

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.pricing.dispatch import option_greeks


def compute_vanna(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
    exercise_style: ExerciseStyle,
) -> float:
    """Vanna: d(delta)/d(sigma).

    Central finite difference with dσ = 0.01.

    Vanna measures how an option's delta changes when implied volatility changes.
    Positive vanna for OTM calls means delta increases as IV rises.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years (must be > 0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: CALL or PUT.
        exercise_style: AMERICAN or EUROPEAN.

    Returns:
        Vanna as float (d(delta)/d(sigma)).
    """
    d_sigma = 0.01

    sigma_up = sigma + d_sigma
    sigma_down = max(sigma - d_sigma, 1e-6)

    delta_up = option_greeks(exercise_style, S, K, T, r, q, sigma_up, option_type).delta
    delta_down = option_greeks(exercise_style, S, K, T, r, q, sigma_down, option_type).delta

    actual_d_sigma = sigma_up - sigma_down
    if actual_d_sigma == 0.0:
        return 0.0

    return (delta_up - delta_down) / actual_d_sigma


def compute_charm(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
    exercise_style: ExerciseStyle,
) -> float:
    """Charm: d(delta)/d(T) (delta decay).

    Central finite difference with dT = 1/365 (one day).
    Falls back to forward difference when T - dT <= 0.

    Charm measures how an option's delta changes as time passes, even without
    a move in the underlying. Important for delta-hedging near expiration.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years (must be > 0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: CALL or PUT.
        exercise_style: AMERICAN or EUROPEAN.

    Returns:
        Charm as float (d(delta)/d(T)).
    """
    d_t = 1.0 / 365.0

    if T - d_t <= 0:
        # Forward difference fallback when T is too small for centered difference
        delta_current = option_greeks(exercise_style, S, K, T, r, q, sigma, option_type).delta
        delta_up = option_greeks(exercise_style, S, K, T + d_t, r, q, sigma, option_type).delta
        return (delta_up - delta_current) / d_t

    # Centered finite difference
    delta_up = option_greeks(exercise_style, S, K, T + d_t, r, q, sigma, option_type).delta
    delta_down = option_greeks(exercise_style, S, K, T - d_t, r, q, sigma, option_type).delta

    return (delta_up - delta_down) / (2.0 * d_t)


def compute_vomma(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
    exercise_style: ExerciseStyle,
) -> float:
    """Vomma: d(vega)/d(sigma) (vega convexity).

    Central finite difference with dσ = 0.01.

    Vomma measures how an option's vega changes when implied volatility changes.
    High vomma means vega is sensitive to vol — important for vol-of-vol risk.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years (must be > 0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: CALL or PUT.
        exercise_style: AMERICAN or EUROPEAN.

    Returns:
        Vomma as float (d(vega)/d(sigma)).
    """
    d_sigma = 0.01

    sigma_up = sigma + d_sigma
    sigma_down = max(sigma - d_sigma, 1e-6)

    vega_up = option_greeks(exercise_style, S, K, T, r, q, sigma_up, option_type).vega
    vega_down = option_greeks(exercise_style, S, K, T, r, q, sigma_down, option_type).vega

    actual_d_sigma = sigma_up - sigma_down
    if actual_d_sigma == 0.0:
        return 0.0

    return (vega_up - vega_down) / actual_d_sigma
