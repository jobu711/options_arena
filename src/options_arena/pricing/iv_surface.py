"""IV surface batch utilities.

Extract ATM implied volatility, compute IV at target deltas, and batch-solve
IV across multiple contracts. All functions are synchronous pure math operating
on pre-fetched data.

Architecture rules:
- Import from ``pricing/dispatch`` only — never ``pricing/bsm`` or ``pricing/american``.
- Functions take typed inputs (``list[OptionContract]``, ``float``, etc.).
- Return ``float | None`` (``None`` when data is insufficient).
- Guard all numerics with ``math.isfinite()``.
"""

import logging
import math

from options_arena.models.config import PricingConfig
from options_arena.models.options import OptionContract
from options_arena.pricing.dispatch import option_greeks, option_iv

logger = logging.getLogger(__name__)


def extract_atm_iv(
    chain_calls: list[OptionContract],
    chain_puts: list[OptionContract],
    spot: float,
) -> float | None:
    """Find the ATM strike and return the average IV of the ATM call and put.

    ATM is defined as the strike closest to ``spot``. If both call and put
    exist at the ATM strike, the result is their average ``market_iv``. If
    only one side exists, that side's IV is returned. Returns ``None`` if
    both chains are empty or ATM IV is non-finite.

    Args:
        chain_calls: List of call ``OptionContract`` objects for a single expiration.
        chain_puts: List of put ``OptionContract`` objects for a single expiration.
        spot: Current underlying price.

    Returns:
        ATM implied volatility as a float, or ``None`` if unavailable.
    """
    if not math.isfinite(spot) or spot <= 0.0:
        return None

    all_contracts = list(chain_calls) + list(chain_puts)
    if not all_contracts:
        return None

    # Find the strike closest to spot
    atm_strike = min(
        {float(c.strike) for c in all_contracts},
        key=lambda s: abs(s - spot),
    )

    # Collect IVs at ATM strike
    ivs: list[float] = []
    for c in chain_calls:
        if float(c.strike) == atm_strike and math.isfinite(c.market_iv) and c.market_iv > 0.0:
            ivs.append(c.market_iv)
    for c in chain_puts:
        if float(c.strike) == atm_strike and math.isfinite(c.market_iv) and c.market_iv > 0.0:
            ivs.append(c.market_iv)

    if not ivs:
        return None

    avg_iv = sum(ivs) / len(ivs)
    return avg_iv if math.isfinite(avg_iv) else None


def extract_atm_iv_by_dte(
    chains_by_dte: dict[int, tuple[list[OptionContract], list[OptionContract]]],
    spot: float,
) -> dict[int, float]:
    """Extract ATM IV at multiple DTEs.

    Args:
        chains_by_dte: Mapping of DTE -> (calls, puts) for each expiration.
        spot: Current underlying price.

    Returns:
        Mapping of DTE -> ATM IV. Only includes DTEs where ATM IV was
        successfully extracted (non-``None``).
    """
    result: dict[int, float] = {}
    for dte, (calls, puts) in chains_by_dte.items():
        iv = extract_atm_iv(calls, puts, spot)
        if iv is not None:
            result[dte] = iv
    return result


def compute_iv_at_delta(
    chain: list[OptionContract],
    target_delta: float,
    spot: float,
    r: float,
    q: float,
    T: float,  # noqa: N803
) -> float | None:
    """Find the IV of the contract whose delta is closest to ``target_delta``.

    Computes Greeks for each contract in ``chain`` via ``pricing/dispatch`` and
    selects the one whose absolute delta is closest to ``abs(target_delta)``.

    For puts, delta is negative; the comparison uses absolute values so
    ``target_delta=0.25`` matches a put with delta=-0.25.

    Args:
        chain: List of ``OptionContract`` objects (same type and expiration).
        target_delta: Target delta magnitude (e.g. 0.25 for 25-delta).
        spot: Current underlying price.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        T: Time to expiration in years (DTE / 365.0). Must be > 0.

    Returns:
        IV of the contract closest to ``target_delta``, or ``None`` if the
        chain is empty or all delta computations fail.
    """
    if not chain:
        return None
    if not math.isfinite(spot) or spot <= 0.0:
        return None
    if not math.isfinite(T) or T <= 0.0:
        return None
    if not math.isfinite(target_delta):
        return None

    best_iv: float | None = None
    best_delta_diff = float("inf")

    for contract in chain:
        sigma = contract.market_iv
        if not math.isfinite(sigma) or sigma <= 0.0:
            continue

        strike = float(contract.strike)
        if not math.isfinite(strike) or strike <= 0.0:
            continue

        try:
            greeks = option_greeks(
                contract.exercise_style, spot, strike, T, r, q, sigma, contract.option_type
            )
            delta_diff = abs(abs(greeks.delta) - abs(target_delta))
            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                best_iv = sigma
        except (ValueError, ZeroDivisionError):
            logger.debug(
                "Greeks computation failed for %s strike=%.2f, skipping",
                contract.ticker,
                strike,
            )
            continue

    return best_iv


def batch_iv_solve(
    contracts: list[OptionContract],
    spot: float,
    r: float,
    q: float,
    config: PricingConfig | None = None,
) -> list[float | None]:
    """Batch-solve implied volatility for a list of contracts.

    Uses ``pricing/dispatch.option_iv`` for each contract. Returns ``None``
    for contracts where the IV solver fails (e.g. market price below intrinsic,
    expired contracts, or non-finite inputs).

    Args:
        contracts: List of ``OptionContract`` objects.
        spot: Current underlying price.
        r: Risk-free rate (annualized, decimal).
        q: Continuous dividend yield (decimal).
        config: Solver configuration. Uses ``PricingConfig()`` defaults if ``None``.

    Returns:
        List of solved IV values (or ``None`` per contract on failure),
        in the same order as ``contracts``.
    """
    if config is None:
        config = PricingConfig()

    results: list[float | None] = []

    for contract in contracts:
        iv = _solve_single_iv(contract, spot, r, q, config)
        results.append(iv)

    return results


def _solve_single_iv(
    contract: OptionContract,
    spot: float,
    r: float,
    q: float,
    config: PricingConfig,
) -> float | None:
    """Solve IV for a single contract, returning None on any failure."""
    if not math.isfinite(spot) or spot <= 0.0:
        return None

    strike = float(contract.strike)
    if not math.isfinite(strike) or strike <= 0.0:
        return None

    mid_price = float(contract.mid)
    if not math.isfinite(mid_price) or mid_price <= 0.0:
        return None

    dte = contract.dte
    if dte <= 0:
        return None

    T = dte / 365.0  # noqa: N806

    try:
        iv = option_iv(
            contract.exercise_style,
            mid_price,
            spot,
            strike,
            T,
            r,
            q,
            contract.option_type,
            config,
        )
        if math.isfinite(iv) and iv > 0.0:
            return iv
        return None
    except (ValueError, ZeroDivisionError, RuntimeError):
        logger.debug(
            "IV solve failed for %s %s strike=%.2f dte=%d",
            contract.ticker,
            contract.option_type.value,
            strike,
            dte,
        )
        return None
