"""Black-Scholes-Merton European option pricing with continuous dividend yield.

Implements the Merton (1973) extension of BSM with continuous dividend yield ``q``.
All functions accept scalar ``float`` arguments and return either ``float`` (prices, IV)
or ``OptionGreeks`` (Greeks). No API calls, no pandas, no raw dicts.

Functions:
    bsm_price  — European option price (call or put).
    bsm_greeks — All 5 analytical Greeks as ``OptionGreeks(pricing_model=BSM)``.
    bsm_vega   — Standalone vega for Newton-Raphson ``fprime`` parameter.
    bsm_iv     — Newton-Raphson implied volatility solver.
"""

import logging
import math

from scipy.stats import norm

from options_arena.models.config import PricingConfig
from options_arena.models.enums import OptionType, PricingModel
from options_arena.models.options import OptionGreeks

logger = logging.getLogger(__name__)

# Solver bounds for implied volatility.
_IV_LOWER_BOUND: float = 1e-6
_IV_UPPER_BOUND: float = 5.0

# Threshold below which sigma * sqrt(T) is treated as effectively zero.
_SIGMA_SQRT_T_EPSILON: float = 1e-12

# Threshold below which vega is too small for Newton-Raphson to make progress.
_VEGA_EPSILON: float = 1e-12


def _d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    """Compute d1 and d2 for the BSM model.

    Args:
        S: Spot price (current underlying price).
        K: Strike price.
        T: Time to expiration in years (DTE / 365.0). Must be > 0.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal). Must be > 0.

    Returns:
        Tuple of (d1, d2).
    """
    sigma_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + sigma * sigma / 2.0) * T) / sigma_sqrt_t
    d2 = d1 - sigma_sqrt_t
    return d1, d2


def _intrinsic_value(S: float, K: float, option_type: OptionType) -> float:
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


def _is_itm(S: float, K: float, option_type: OptionType) -> bool:
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


def bsm_price(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> float:
    """Compute the European option price using Black-Scholes-Merton with dividends.

    Uses the Merton (1973) extension with continuous dividend yield ``q``:

    - Call = S * e^(-qT) * N(d1) - K * e^(-rT) * N(d2)
    - Put  = K * e^(-rT) * N(-d2) - S * e^(-qT) * N(-d1)

    Args:
        S: Spot price (current underlying price).
        K: Strike price.
        T: Time to expiration in years (DTE / 365.0).
        r: Risk-free rate (annualized, decimal: 0.05 = 5%).
        q: Continuous dividend yield (decimal: 0.02 = 2%).
        sigma: Implied volatility (annualized, decimal: 0.30 = 30%).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.

    Returns:
        European option price as float.
    """
    # Edge case: at or past expiration — return intrinsic value.
    if T <= 0.0:
        return _intrinsic_value(S, K, option_type)

    # Edge case: sigma effectively zero — return discounted intrinsic value.
    sigma_sqrt_t = sigma * math.sqrt(T)
    if sigma <= 0.0 or sigma_sqrt_t < _SIGMA_SQRT_T_EPSILON:
        discount_r = math.exp(-r * T)
        discount_q = math.exp(-q * T)
        match option_type:
            case OptionType.CALL:
                return max(S * discount_q - K * discount_r, 0.0)
            case OptionType.PUT:
                return max(K * discount_r - S * discount_q, 0.0)

    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    discount_r = math.exp(-r * T)
    discount_q = math.exp(-q * T)

    match option_type:
        case OptionType.CALL:
            price: float = S * discount_q * norm.cdf(d1) - K * discount_r * norm.cdf(d2)
        case OptionType.PUT:
            price = K * discount_r * norm.cdf(-d2) - S * discount_q * norm.cdf(-d1)

    return price


def bsm_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> OptionGreeks:
    """Compute all 5 analytical BSM Greeks.

    Returns an ``OptionGreeks`` instance with ``pricing_model=PricingModel.BSM``.
    All Greeks use closed-form solutions (no finite differences).

    Args:
        S: Spot price (current underlying price).
        K: Strike price.
        T: Time to expiration in years (DTE / 365.0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.

    Returns:
        ``OptionGreeks`` with delta, gamma, theta, vega, rho, and pricing_model=BSM.
    """
    # Edge case: at or past expiration — boundary Greeks.
    if T <= 0.0:
        return _boundary_greeks(S, K, option_type)

    # Edge case: sigma effectively zero — boundary Greeks.
    sigma_sqrt_t = sigma * math.sqrt(T)
    if sigma <= 0.0 or sigma_sqrt_t < _SIGMA_SQRT_T_EPSILON:
        return _boundary_greeks(S, K, option_type)

    d1, d2 = _d1_d2(S, K, T, r, q, sigma)
    sqrt_t = math.sqrt(T)
    discount_r = math.exp(-r * T)
    discount_q = math.exp(-q * T)
    n_d1: float = norm.pdf(d1)  # Standard normal density at d1.
    nd1_cdf: float = norm.cdf(d1)
    nd2_cdf: float = norm.cdf(d2)
    n_neg_d1_cdf: float = norm.cdf(-d1)
    n_neg_d2_cdf: float = norm.cdf(-d2)

    # Gamma is the same for calls and puts.
    gamma = discount_q * n_d1 / (S * sigma * sqrt_t)

    # Vega is the same for calls and puts.
    vega = S * discount_q * n_d1 * sqrt_t

    # Common theta component: -(S * sigma * e^(-qT) * n(d1)) / (2 * sqrt(T))
    theta_common = -(S * sigma * discount_q * n_d1) / (2.0 * sqrt_t)

    match option_type:
        case OptionType.CALL:
            delta = discount_q * nd1_cdf
            theta = theta_common + q * S * discount_q * nd1_cdf - r * K * discount_r * nd2_cdf
            rho = K * T * discount_r * nd2_cdf
        case OptionType.PUT:
            delta = -discount_q * n_neg_d1_cdf
            theta = (
                theta_common
                - q * S * discount_q * n_neg_d1_cdf
                + r * K * discount_r * n_neg_d2_cdf
            )
            rho = -K * T * discount_r * n_neg_d2_cdf

    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=PricingModel.BSM,
    )


def _boundary_greeks(S: float, K: float, option_type: OptionType) -> OptionGreeks:
    """Return boundary Greeks when T <= 0 or sigma <= 0.

    At expiration or with zero volatility:
    - Delta = 1.0 (call ITM) or 0.0 (call OTM); -1.0 (put ITM) or 0.0 (put OTM).
    - Gamma, vega, rho, theta = 0.0.

    Args:
        S: Spot price.
        K: Strike price.
        option_type: CALL or PUT.

    Returns:
        ``OptionGreeks`` with boundary values.
    """
    itm = _is_itm(S, K, option_type)

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
        pricing_model=PricingModel.BSM,
    )


def bsm_vega(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
) -> float:
    """Compute standalone BSM vega for Newton-Raphson IV solver ``fprime``.

    ``vega = S * e^(-qT) * n(d1) * sqrt(T)``

    This is the same formula as vega in ``bsm_greeks`` but as a standalone float
    for use as the ``fprime`` argument in Newton-Raphson iteration.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).

    Returns:
        Vega as float. Returns 0.0 when T <= 0 or sigma <= 0.
    """
    if T <= 0.0 or sigma <= 0.0:
        return 0.0

    sigma_sqrt_t = sigma * math.sqrt(T)
    if sigma_sqrt_t < _SIGMA_SQRT_T_EPSILON:
        return 0.0

    d1, _ = _d1_d2(S, K, T, r, q, sigma)
    sqrt_t = math.sqrt(T)
    discount_q = math.exp(-q * T)
    n_d1: float = norm.pdf(d1)

    return S * discount_q * n_d1 * sqrt_t


def bsm_iv(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    option_type: OptionType,
    initial_guess: float = 0.30,
    config: PricingConfig | None = None,
) -> float:
    """Solve for implied volatility using Newton-Raphson with analytical vega.

    Uses ``bsm_price`` as the objective and ``bsm_vega`` as the derivative
    (``fprime``), providing quadratic convergence (~5-8 iterations typical).

    Args:
        market_price: Observed market price of the option.
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years (must be > 0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.
        initial_guess: Starting sigma for iteration (default 0.30).
        config: Solver configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        Implied volatility as float (annualized, decimal).

    Raises:
        ValueError: If the solver does not converge within ``max_iter`` iterations,
            if vega is too small to make progress, or if ``market_price <= 0``.
    """
    if config is None:
        config = PricingConfig()

    tol = config.iv_solver_tol
    max_iter = config.iv_solver_max_iter

    if market_price <= 0.0:
        raise ValueError(f"market_price must be > 0 for IV computation, got {market_price}")

    if T <= 0.0:
        raise ValueError(f"T must be > 0 for IV computation, got {T}")

    sigma = initial_guess

    for i in range(max_iter):
        # Clamp sigma to valid bounds.
        sigma = max(_IV_LOWER_BOUND, min(sigma, _IV_UPPER_BOUND))

        price = bsm_price(S, K, T, r, q, sigma, option_type)
        price_diff = price - market_price

        if abs(price_diff) < tol:
            logger.debug("BSM IV converged in %d iterations: sigma=%.6f", i + 1, sigma)
            return sigma

        vega = bsm_vega(S, K, T, r, q, sigma)

        if abs(vega) < _VEGA_EPSILON:
            raise ValueError(
                f"BSM IV solver: vega too small ({vega:.2e}) at sigma={sigma:.6f}, "
                f"iteration {i + 1}. Cannot make progress. "
                f"Inputs: S={S}, K={K}, T={T}, r={r}, q={q}, "
                f"option_type={option_type}, market_price={market_price}"
            )

        # Newton-Raphson step.
        sigma = sigma - price_diff / vega

        # Clamp after update.
        sigma = max(_IV_LOWER_BOUND, min(sigma, _IV_UPPER_BOUND))

    # Did not converge within max_iter iterations.
    final_price = bsm_price(S, K, T, r, q, sigma, option_type)
    raise ValueError(
        f"BSM IV solver did not converge after {max_iter} iterations. "
        f"Final sigma={sigma:.6f}, final price={final_price:.6f}, "
        f"market_price={market_price:.6f}, "
        f"residual={abs(final_price - market_price):.2e}. "
        f"Inputs: S={S}, K={K}, T={T}, r={r}, q={q}, option_type={option_type}"
    )
