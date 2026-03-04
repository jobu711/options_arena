"""Barone-Adesi-Whaley (1987) analytical approximation for American option pricing.

Adds an early exercise premium to the European BSM price. The critical stock price
(exercise boundary) is found via Newton-Raphson iteration on the boundary condition.

Functions:
    american_price  -- American option price via BAW analytical approximation.
    american_greeks -- Finite-difference bump-and-reprice Greeks (``OptionGreeks``).
    american_iv     -- Implied volatility solver using ``scipy.optimize.brentq``.

Key identities enforced by this implementation:
    FR-P4: When ``q = 0``, ``american_call == bsm_call`` (no early exercise for calls
           on non-dividend-paying stocks).
    FR-P5: ``american_put >= bsm_put`` always (early exercise premium is non-negative).
"""

import logging
import math

from scipy.optimize import brentq
from scipy.stats import norm

from options_arena.models.config import PricingConfig
from options_arena.models.enums import OptionType, PricingModel
from options_arena.models.options import OptionGreeks
from options_arena.pricing._common import (
    boundary_greeks,
    intrinsic_value,
    validate_positive_inputs,
)
from options_arena.pricing.bsm import bsm_price

logger = logging.getLogger(__name__)

# Solver bounds for implied volatility (same as BSM module).
_IV_LOWER_BOUND: float = 1e-6
_IV_UPPER_BOUND: float = 5.0

# Convergence tolerance for critical price Newton-Raphson.
_CRITICAL_PRICE_TOL: float = 1e-8

# Maximum iterations for critical price solver.
_CRITICAL_PRICE_MAX_ITER: int = 200

# Threshold below which K_param (1 - exp(-rT)) is too small for BAW premium.
_K_PARAM_EPSILON: float = 1e-12

# Threshold below which sigma * sqrt(T) is effectively zero.
_SIGMA_SQRT_T_EPSILON: float = 1e-12

# Finite-difference bump sizes.
_DS_FRACTION: float = 0.01  # 1% of spot for price-based Greeks.
_DT: float = 1.0 / 365.0  # One day.
_DSIGMA: float = 0.001  # 0.1 vol point.
_DR: float = 0.001  # 10 basis points.


def _d1(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """Compute d1 for the BSM model (needed for BAW boundary condition).

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years. Must be > 0.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal). Must be > 0.

    Returns:
        d1 value.
    """
    sigma_sqrt_t = sigma * math.sqrt(T)
    return (math.log(S / K) + (r - q + sigma * sigma / 2.0) * T) / sigma_sqrt_t


def _baw_auxiliary_params(
    r: float, q: float, sigma: float, T: float
) -> tuple[float, float, float]:
    """Compute BAW auxiliary parameters M, N_param, K_param.

    Args:
        r: Risk-free rate.
        q: Continuous dividend yield.
        sigma: Implied volatility.
        T: Time to expiration in years.

    Returns:
        Tuple of (M, N_param, K_param).
    """
    sigma_sq = sigma * sigma
    M = 2.0 * r / sigma_sq
    N_param = 2.0 * (r - q) / sigma_sq
    K_param = 1.0 - math.exp(-r * T)
    return M, N_param, K_param


def _find_critical_price_call(
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    q2: float,
) -> float:
    """Find the critical stock price S* for an American call via Newton-Raphson.

    At S*, the early exercise value ``S* - K`` equals the continuation value.
    The boundary condition is:

        S* - K = bsm_call(S*) + (1 - e^(-qT) * N(d1(S*))) * S* / q2

    We solve for S* such that the residual is zero.

    Args:
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate.
        q: Continuous dividend yield.
        sigma: Implied volatility.
        q2: BAW auxiliary parameter for calls.

    Returns:
        Critical stock price S*.
    """
    discount_q = math.exp(-q * T)

    # Seed: start above the strike. Use a BSM-derived heuristic.
    # S* is typically K / (1 - 2 / q2) for the perpetual case; use K as initial seed.
    S_star = K / (1.0 - 2.0 / q2) if q2 > 2.0 else K * 1.5

    # Ensure S_star > K (for calls, exercise boundary is above the strike).
    S_star = max(S_star, K * 1.001)

    for _ in range(_CRITICAL_PRICE_MAX_ITER):
        bsm_call_val = bsm_price(S_star, K, T, r, q, sigma, OptionType.CALL)
        d1_val = _d1(S_star, K, T, r, q, sigma)
        n_d1: float = norm.cdf(d1_val)

        # LHS of boundary: exercise value
        lhs: float = S_star - K

        # RHS of boundary: continuation value = BSM_call + A2_factor * S_star / q2
        # where A2_factor = (1 - e^(-qT) * N(d1))
        A2_factor: float = 1.0 - discount_q * n_d1
        rhs: float = bsm_call_val + A2_factor * S_star / q2

        # Residual: LHS - RHS = 0 at critical price.
        residual: float = lhs - rhs

        if abs(residual) < _CRITICAL_PRICE_TOL:
            return S_star

        # Derivative of residual w.r.t. S_star:
        # d(LHS)/dS = 1
        # d(RHS)/dS = delta_bsm + (1/q2) * (1 - e^(-qT)*N(d1))
        #           + (S*/q2) * (-e^(-qT) * n(d1) * d(d1)/dS)
        # d(d1)/dS = 1 / (S * sigma * sqrt(T))
        sigma_sqrt_t = sigma * math.sqrt(T)
        dd1_dS = 1.0 / (S_star * sigma_sqrt_t)
        n_d1_pdf: float = norm.pdf(d1_val)

        delta_bsm: float = discount_q * n_d1
        d_rhs_dS: float = (
            delta_bsm + A2_factor / q2 - (S_star / q2) * discount_q * n_d1_pdf * dd1_dS
        )

        d_residual_dS: float = 1.0 - d_rhs_dS

        # Avoid division by near-zero derivative.
        if abs(d_residual_dS) < 1e-14:
            break

        # Newton step.
        S_star = S_star - residual / d_residual_dS

        # Ensure S_star remains positive and above K.
        S_star = max(S_star, K * 1.001)

    logger.warning(
        "BAW critical price (call) did not converge after %d iterations. "
        "Using last estimate S*=%.6f for K=%.2f, T=%.4f, sigma=%.4f",
        _CRITICAL_PRICE_MAX_ITER,
        S_star,
        K,
        T,
        sigma,
    )
    return S_star


def _find_critical_price_put(
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    q1: float,
) -> float:
    """Find the critical stock price S** for an American put via Newton-Raphson.

    At S**, the early exercise value ``K - S**`` equals the continuation value.
    The boundary condition is:

        K - S** = bsm_put(S**) - (1 - e^(-qT) * N(-d1(S**))) * S** / q1

    Args:
        K: Strike price.
        T: Time to expiration in years.
        r: Risk-free rate.
        q: Continuous dividend yield.
        sigma: Implied volatility.
        q1: BAW auxiliary parameter for puts (q1 < 0).

    Returns:
        Critical stock price S**.
    """
    discount_q = math.exp(-q * T)

    # Seed: start below the strike. Use a perpetual approximation heuristic.
    # For the perpetual put, S** = K / (1 - 2 / q1). Since q1 < 0, this gives S** < K.
    S_star_star = K / (1.0 - 2.0 / q1) if q1 < -2.0 else K * 0.5

    # Ensure 0 < S** < K.
    S_star_star = max(S_star_star, K * 0.001)
    S_star_star = min(S_star_star, K * 0.999)

    for _ in range(_CRITICAL_PRICE_MAX_ITER):
        bsm_put_val = bsm_price(S_star_star, K, T, r, q, sigma, OptionType.PUT)
        d1_val = _d1(S_star_star, K, T, r, q, sigma)
        n_neg_d1: float = norm.cdf(-d1_val)

        # LHS of boundary: exercise value.
        lhs: float = K - S_star_star

        # RHS of boundary: continuation value = BSM_put - A1_factor * S** / q1
        # where A1_factor = (1 - e^(-qT) * N(-d1))
        # Note: q1 < 0, so -S**/q1 > 0, making the early exercise premium positive.
        A1_factor: float = 1.0 - discount_q * n_neg_d1
        rhs: float = bsm_put_val - A1_factor * S_star_star / q1

        residual: float = lhs - rhs

        if abs(residual) < _CRITICAL_PRICE_TOL:
            return S_star_star

        # Derivative of residual w.r.t. S**:
        # d(LHS)/dS = -1
        # d(RHS)/dS = delta_bsm_put - (1/q1)*(1 - e^(-qT)*N(-d1))
        #           - (S**/q1) * (e^(-qT) * n(d1) * d(d1)/dS)
        # Note: d(N(-d1))/dS = -n(d1) * d(d1)/dS  (chain rule with negation).
        sigma_sqrt_t = sigma * math.sqrt(T)
        dd1_dS = 1.0 / (S_star_star * sigma_sqrt_t)
        n_d1_pdf: float = norm.pdf(d1_val)

        delta_bsm_put: float = -discount_q * n_neg_d1
        d_rhs_dS: float = (
            delta_bsm_put - A1_factor / q1 - (S_star_star / q1) * discount_q * n_d1_pdf * dd1_dS
        )

        d_residual_dS: float = -1.0 - d_rhs_dS

        if abs(d_residual_dS) < 1e-14:
            break

        S_star_star = S_star_star - residual / d_residual_dS

        # Ensure S** remains positive and below K.
        S_star_star = max(S_star_star, K * 0.001)
        S_star_star = min(S_star_star, K * 0.999)

    logger.warning(
        "BAW critical price (put) did not converge after %d iterations. "
        "Using last estimate S**=%.6f for K=%.2f, T=%.4f, sigma=%.4f",
        _CRITICAL_PRICE_MAX_ITER,
        S_star_star,
        K,
        T,
        sigma,
    )
    return S_star_star


def american_price(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> float:
    """Compute American option price using the Barone-Adesi-Whaley approximation.

    Adds an early exercise premium to the European BSM price. For calls with
    ``q = 0``, the premium is zero and the result equals ``bsm_price`` exactly
    (FR-P4 identity). For puts, the result is always ``>= bsm_price`` (FR-P5).

    Args:
        S: Spot price (current underlying price).
        K: Strike price.
        T: Time to expiration in years (DTE / 365.0).
        r: Risk-free rate (annualized, decimal: 0.05 = 5%).
        q: Continuous dividend yield (decimal: 0.02 = 2%).
        sigma: Implied volatility (annualized, decimal: 0.30 = 30%).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.

    Returns:
        American option price as float.

    Raises:
        ValueError: If S <= 0 or K <= 0.
    """
    validate_positive_inputs(S, K, T, r)
    if not math.isfinite(q):
        raise ValueError(f"q must be a finite number, got {q}")

    # Edge case: at or past expiration -- return intrinsic value.
    if T <= 0.0:
        return intrinsic_value(S, K, option_type)

    # Edge case: non-finite or non-positive sigma -- return intrinsic value.
    if not math.isfinite(sigma) or sigma <= 0.0:
        return intrinsic_value(S, K, option_type)

    sigma_sqrt_t = sigma * math.sqrt(T)
    if sigma_sqrt_t < _SIGMA_SQRT_T_EPSILON:
        return intrinsic_value(S, K, option_type)

    # FR-P4: When q=0, American call == European call (no early exercise premium).
    # Return BSM directly to ensure exact equality (not just approximate).
    if option_type == OptionType.CALL and q == 0.0:
        return bsm_price(S, K, T, r, q, sigma, option_type)

    # When r is very small, K_param approaches 0 and the early exercise premium
    # vanishes. Return BSM price to avoid numerical instability.
    K_param = 1.0 - math.exp(-r * T)
    if abs(K_param) < _K_PARAM_EPSILON:
        return bsm_price(S, K, T, r, q, sigma, option_type)

    # Compute auxiliary parameters.
    M, N_param, _ = _baw_auxiliary_params(r, q, sigma, T)

    discriminant = (N_param - 1.0) ** 2 + 4.0 * M / K_param

    # The discriminant should always be positive for valid inputs, but guard.
    if discriminant < 0.0:
        logger.warning(
            "BAW discriminant negative (%.2e) -- falling back to BSM. "
            "S=%.2f, K=%.2f, T=%.4f, r=%.4f, q=%.4f, sigma=%.4f",
            discriminant,
            S,
            K,
            T,
            r,
            q,
            sigma,
        )
        return bsm_price(S, K, T, r, q, sigma, option_type)

    sqrt_disc = math.sqrt(discriminant)

    match option_type:
        case OptionType.CALL:
            return _baw_call(S, K, T, r, q, sigma, N_param, sqrt_disc, K_param)
        case OptionType.PUT:
            return _baw_put(S, K, T, r, q, sigma, N_param, sqrt_disc, K_param)


def _baw_call(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    N_param: float,
    sqrt_disc: float,
    K_param: float,
) -> float:
    """BAW pricing for an American call.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration.
        r: Risk-free rate.
        q: Continuous dividend yield.
        sigma: Implied volatility.
        N_param: BAW N parameter.
        sqrt_disc: Square root of discriminant.
        K_param: BAW K parameter.

    Returns:
        American call price.
    """
    q2 = (-(N_param - 1.0) + sqrt_disc) / 2.0

    # Find critical price S*.
    S_star = _find_critical_price_call(K, T, r, q, sigma, q2)

    # If S >= S*, immediate exercise is optimal.
    if S_star <= S:
        return S - K

    # Compute early exercise premium coefficient A2.
    discount_q = math.exp(-q * T)
    d1_star = _d1(S_star, K, T, r, q, sigma)
    n_d1_star: float = norm.cdf(d1_star)
    A2: float = (S_star / q2) * (1.0 - discount_q * n_d1_star)

    # American call = European call + early exercise premium.
    european_price: float = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
    premium: float = A2 * (S / S_star) ** q2

    result: float = european_price + premium
    return result


def _baw_put(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    N_param: float,
    sqrt_disc: float,
    K_param: float,
) -> float:
    """BAW pricing for an American put.

    Args:
        S: Spot price.
        K: Strike price.
        T: Time to expiration.
        r: Risk-free rate.
        q: Continuous dividend yield.
        sigma: Implied volatility.
        N_param: BAW N parameter.
        sqrt_disc: Square root of discriminant.
        K_param: BAW K parameter.

    Returns:
        American put price.
    """
    q1 = (-(N_param - 1.0) - sqrt_disc) / 2.0

    # Find critical price S**.
    S_star_star = _find_critical_price_put(K, T, r, q, sigma, q1)

    # If S <= S**, immediate exercise is optimal.
    if S_star_star >= S:
        return K - S

    # Compute early exercise premium coefficient A1.
    discount_q = math.exp(-q * T)
    d1_star_star = _d1(S_star_star, K, T, r, q, sigma)
    n_neg_d1_star_star: float = norm.cdf(-d1_star_star)
    A1: float = -(S_star_star / q1) * (1.0 - discount_q * n_neg_d1_star_star)

    # American put = European put + early exercise premium.
    european_price: float = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
    premium: float = A1 * (S / S_star_star) ** q1

    result: float = european_price + premium
    return result


def american_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    sigma: float,
    option_type: OptionType,
) -> OptionGreeks:
    """Compute American option Greeks via finite-difference bump-and-reprice.

    BAW has no analytical Greeks. All sensitivities are computed using centered
    finite differences (or forward difference for theta when ``T`` is small).

    Args:
        S: Spot price (current underlying price).
        K: Strike price.
        T: Time to expiration in years (DTE / 365.0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        sigma: Implied volatility (annualized, decimal).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.

    Returns:
        ``OptionGreeks`` with ``pricing_model=PricingModel.BAW``.

    Raises:
        ValueError: If S <= 0 or K <= 0.
    """
    validate_positive_inputs(S, K, T, r)
    if not math.isfinite(q):
        raise ValueError(f"q must be a finite number, got {q}")

    # Guard: sigma must be finite (NaN/Inf would corrupt all bump-and-reprice Greeks)
    if not math.isfinite(sigma):
        raise ValueError(f"sigma must be a finite number, got {sigma}")

    # Edge case: at or past expiration or sigma effectively zero.
    if T <= 0.0 or sigma <= 0.0:
        return boundary_greeks(S, K, option_type, PricingModel.BAW)

    sigma_sqrt_t = sigma * math.sqrt(T)
    if sigma_sqrt_t < _SIGMA_SQRT_T_EPSILON:
        return boundary_greeks(S, K, option_type, PricingModel.BAW)

    # Base price.
    price_base = american_price(S, K, T, r, q, sigma, option_type)

    # Bump sizes.
    dS = _DS_FRACTION * S
    dT = _DT
    dSigma = _DSIGMA
    dR = _DR

    # Delta: centered difference on S.
    price_up_S = american_price(S + dS, K, T, r, q, sigma, option_type)
    price_dn_S = american_price(S - dS, K, T, r, q, sigma, option_type)
    delta = (price_up_S - price_dn_S) / (2.0 * dS)

    # Gamma: second derivative w.r.t. S.
    gamma = (price_up_S - 2.0 * price_base + price_dn_S) / (dS * dS)

    # Theta: use backward difference if T > dT, else forward difference.
    # Theta = (price(T - dT) - price(T)) / dT  (backward; price decreases as T shrinks).
    # When T is small, use forward: theta = (price(T) - price(T + dT)) / dT.
    if dT < T:
        price_T_minus = american_price(S, K, T - dT, r, q, sigma, option_type)
        theta = (price_T_minus - price_base) / dT
    else:
        price_T_plus = american_price(S, K, T + dT, r, q, sigma, option_type)
        theta = (price_base - price_T_plus) / dT

    # Vega: centered difference on sigma (clamp lower bound to avoid negative sigma).
    sigma_up = sigma + dSigma
    sigma_dn = max(sigma - dSigma, _IV_LOWER_BOUND)
    price_up_sigma = american_price(S, K, T, r, q, sigma_up, option_type)
    price_dn_sigma = american_price(S, K, T, r, q, sigma_dn, option_type)
    vega = (price_up_sigma - price_dn_sigma) / (sigma_up - sigma_dn)

    # Rho: centered difference on r.
    price_up_r = american_price(S, K, T, r + dR, q, sigma, option_type)
    price_dn_r = american_price(S, K, T, r - dR, q, sigma, option_type)
    rho = (price_up_r - price_dn_r) / (2.0 * dR)

    # Clamp delta to [-1, 1] (finite differences can slightly exceed bounds).
    delta = max(-1.0, min(1.0, delta))

    # Clamp gamma and vega to >= 0 (numerical noise can make them slightly negative).
    gamma = max(0.0, gamma)
    vega = max(0.0, vega)

    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=PricingModel.BAW,
    )


def american_iv(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    option_type: OptionType,
    config: PricingConfig | None = None,
) -> float:
    """Solve for implied volatility of an American option using ``brentq``.

    Uses ``scipy.optimize.brentq`` (bracket-based root finder), NOT Newton-Raphson,
    because BAW has no analytical vega w.r.t. IV. Option price is monotonically
    increasing in sigma, so the bracket ``[1e-6, 5.0]`` always contains the root
    for valid market prices.

    Args:
        market_price: Observed market price of the American option.
        S: Spot price.
        K: Strike price.
        T: Time to expiration in years (must be > 0).
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        option_type: ``OptionType.CALL`` or ``OptionType.PUT``.
        config: Solver configuration. Uses ``PricingConfig()`` defaults if None.

    Returns:
        Implied volatility as float (annualized, decimal).

    Raises:
        ValueError: If ``market_price <= 0``, ``T <= 0``, ``S <= 0``, ``K <= 0``,
            or the solver fails (market price outside theoretical range).
    """
    validate_positive_inputs(S, K, T, r)
    if not math.isfinite(q):
        raise ValueError(f"q must be a finite number, got {q}")

    if config is None:
        config = PricingConfig()

    if not math.isfinite(market_price) or market_price <= 0.0:
        raise ValueError(f"market_price must be a finite number > 0, got {market_price}")

    if T <= 0.0:
        raise ValueError(f"T must be > 0 for IV computation, got {T}")

    def objective(sigma: float) -> float:
        return american_price(S, K, T, r, q, sigma, option_type) - market_price

    try:
        iv: float = brentq(
            objective,
            _IV_LOWER_BOUND,
            _IV_UPPER_BOUND,
            xtol=config.iv_solver_tol,
            maxiter=config.iv_solver_max_iter,
        )
    except ValueError as exc:
        # brentq raises ValueError when the bracket doesn't contain a root
        # (f(a) and f(b) have the same sign), meaning the market price is
        # outside the theoretical range for any sigma in [1e-6, 5.0].
        price_at_lower = american_price(S, K, T, r, q, _IV_LOWER_BOUND, option_type)
        price_at_upper = american_price(S, K, T, r, q, _IV_UPPER_BOUND, option_type)
        raise ValueError(
            f"BAW IV solver: no root in bracket [{_IV_LOWER_BOUND}, {_IV_UPPER_BOUND}]. "
            f"market_price={market_price:.6f}, "
            f"price_at_lower_sigma={price_at_lower:.6f}, "
            f"price_at_upper_sigma={price_at_upper:.6f}. "
            f"Inputs: S={S}, K={K}, T={T}, r={r}, q={q}, option_type={option_type}"
        ) from exc

    logger.debug(
        "BAW IV converged: sigma=%.6f for market_price=%.4f, S=%.2f, K=%.2f",
        iv,
        market_price,
        S,
        K,
    )
    return iv
