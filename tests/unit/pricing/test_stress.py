"""Parametric stress tests for BSM and BAW pricing functions.

Property-based invariant tests (default marker, CI-fast < 30s):
    1. Non-negative price for all finite inputs
    2. Put-call parity (BSM) within tolerance
    3. American >= European for same inputs
    4. Intrinsic floor: price >= max(S-K, 0) for calls, max(K-S, 0) for puts
    5. Price monotonic in S (call increases, put decreases)
    6. Price monotonic in sigma
    7. Price monotonic in T (q=0)
    8. Delta bounds: -1 <= delta <= 1
    9. Gamma non-negative
   10. Vega non-negative

Brute-force grid (@pytest.mark.slow):
    ~2K combos: finite price, non-negative price, finite Greeks, delta in bounds.
"""

import math
from functools import lru_cache

import pytest

from options_arena.models.enums import OptionType
from options_arena.pricing.american import american_greeks, american_price
from options_arena.pricing.bsm import bsm_greeks, bsm_price
from tests.harnesses.pricing_params import (
    PricingParams,
    generate_property_grid,
    generate_stress_grid,
)

# ---------------------------------------------------------------------------
# Lazy grid generation — deferred until first test from this file is collected
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _get_property_grid() -> list[PricingParams]:
    return generate_property_grid()


@lru_cache(maxsize=1)
def _get_stress_grid() -> list[PricingParams]:
    return generate_stress_grid()


def _param_id(p: PricingParams) -> str:
    return f"S={p.S},K={p.K:.1f},T={p.T},sig={p.sigma},r={p.r},q={p.q},{p.option_type.value}"


# ---------------------------------------------------------------------------
# Property 1: Non-negative price
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("p", _get_property_grid(), ids=_param_id)
def test_bsm_price_non_negative(p: PricingParams) -> None:
    """BSM price must be >= 0 for all valid inputs."""
    price = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(price), f"BSM price not finite: {price}"
    assert price >= -1e-10, f"BSM price negative: {price}"


@pytest.mark.parametrize("p", _get_property_grid(), ids=_param_id)
def test_american_price_non_negative(p: PricingParams) -> None:
    """American price must be >= 0 for all valid inputs."""
    price = american_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(price), f"American price not finite: {price}"
    assert price >= -1e-10, f"American price negative: {price}"


# ---------------------------------------------------------------------------
# Property 2: Put-call parity (BSM European)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.option_type == OptionType.CALL],
    ids=_param_id,
)
def test_bsm_put_call_parity(p: PricingParams) -> None:
    """BSM put-call parity: C - P = S*e^(-qT) - K*e^(-rT)."""
    call = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, OptionType.CALL)
    put = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, OptionType.PUT)
    expected = p.S * math.exp(-p.q * p.T) - p.K * math.exp(-p.r * p.T)
    assert call - put == pytest.approx(expected, abs=1e-6), (
        f"Put-call parity violated: C-P={call - put:.8f}, expected={expected:.8f}"
    )


# ---------------------------------------------------------------------------
# Property 3: American >= European
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("p", _get_property_grid(), ids=_param_id)
def test_american_ge_european(p: PricingParams) -> None:
    """American option price must be >= European for identical inputs."""
    eur = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    amer = american_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    # Allow small numerical tolerance (1e-8) for floating point
    assert amer >= eur - 1e-8, f"American ({amer:.8f}) < European ({eur:.8f}) by {eur - amer:.2e}"


# ---------------------------------------------------------------------------
# Property 4: Intrinsic floor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("p", _get_property_grid(), ids=_param_id)
def test_bsm_intrinsic_floor(p: PricingParams) -> None:
    """BSM price must be >= discounted intrinsic value."""
    price = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    intrinsic = max(p.S - p.K, 0.0) if p.option_type == OptionType.CALL else max(p.K - p.S, 0.0)
    # European price can be below intrinsic by at most the discount factor
    discount_gap = p.K * (1.0 - math.exp(-p.r * p.T))
    assert price >= intrinsic - discount_gap - 1e-8, (
        f"BSM price {price:.6f} far below intrinsic {intrinsic:.6f} "
        f"(discount_gap={discount_gap:.6f})"
    )


@pytest.mark.parametrize("p", _get_property_grid(), ids=_param_id)
def test_american_intrinsic_floor(p: PricingParams) -> None:
    """American price must be >= intrinsic value (early exercise)."""
    price = american_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    intrinsic = max(p.S - p.K, 0.0) if p.option_type == OptionType.CALL else max(p.K - p.S, 0.0)
    # American can always be exercised, so price >= intrinsic
    assert price >= intrinsic - 1e-6, f"American price {price:.6f} < intrinsic {intrinsic:.6f}"


# ---------------------------------------------------------------------------
# Property 5: Price monotonic in S
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_bsm_monotonic_in_spot(p: PricingParams) -> None:
    """Call price increases with S; put price decreases with S."""
    dS = p.S * 0.05
    price_lo = bsm_price(p.S - dS, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    price_hi = bsm_price(p.S + dS, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    if p.option_type == OptionType.CALL:
        assert price_hi >= price_lo - 1e-10, "Call not monotonic in S"
    else:
        assert price_lo >= price_hi - 1e-10, "Put not monotonic in S"


# ---------------------------------------------------------------------------
# Property 6: Price monotonic in sigma
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_bsm_monotonic_in_sigma(p: PricingParams) -> None:
    """Option price increases with sigma (positive vega)."""
    d_sigma = 0.05
    price_lo = bsm_price(p.S, p.K, p.T, p.r, p.q, max(p.sigma - d_sigma, 1e-6), p.option_type)
    price_hi = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma + d_sigma, p.option_type)
    assert price_hi >= price_lo - 1e-10, "Price not monotonic in sigma"


# ---------------------------------------------------------------------------
# Property 7: Price monotonic in T (q=0)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.q == 0.0 and p.T >= 0.05 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_bsm_monotonic_in_time_no_div(p: PricingParams) -> None:
    """With q=0, call price increases with T (no early exercise advantage)."""
    if p.option_type == OptionType.PUT:
        pytest.skip("Puts can decrease in T even without dividends (deep ITM)")
    dT = 0.02
    price_lo = bsm_price(p.S, p.K, max(p.T - dT, 1e-4), p.r, p.q, p.sigma, p.option_type)
    price_hi = bsm_price(p.S, p.K, p.T + dT, p.r, p.q, p.sigma, p.option_type)
    assert price_hi >= price_lo - 1e-8, "Call not monotonic in T (q=0)"


# ---------------------------------------------------------------------------
# Property 8: Delta bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.01],
    ids=_param_id,
)
def test_bsm_delta_bounds(p: PricingParams) -> None:
    """BSM delta must be in [-1, 1]."""
    greeks = bsm_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"
    if p.option_type == OptionType.CALL:
        assert greeks.delta >= 0.0, f"Call delta negative: {greeks.delta}"
    else:
        assert greeks.delta <= 0.0, f"Put delta positive: {greeks.delta}"


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.01],
    ids=_param_id,
)
def test_american_delta_bounds(p: PricingParams) -> None:
    """American delta must be in [-1, 1]."""
    greeks = american_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"


# ---------------------------------------------------------------------------
# Property 9: Gamma non-negative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_bsm_gamma_non_negative(p: PricingParams) -> None:
    """BSM gamma must be >= 0."""
    greeks = bsm_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert greeks.gamma >= -1e-10, f"Gamma negative: {greeks.gamma}"


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_american_gamma_non_negative(p: PricingParams) -> None:
    """American gamma must be >= 0 (clamped in implementation)."""
    greeks = american_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert greeks.gamma >= -1e-10, f"Gamma negative: {greeks.gamma}"


# ---------------------------------------------------------------------------
# Property 10: Vega non-negative
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_bsm_vega_non_negative(p: PricingParams) -> None:
    """BSM vega must be >= 0."""
    greeks = bsm_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert greeks.vega >= -1e-10, f"Vega negative: {greeks.vega}"


@pytest.mark.parametrize(
    "p",
    [p for p in _get_property_grid() if p.T >= 0.01 and p.sigma >= 0.05],
    ids=_param_id,
)
def test_american_vega_non_negative(p: PricingParams) -> None:
    """American vega must be >= 0 (clamped in implementation)."""
    greeks = american_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert greeks.vega >= -1e-10, f"Vega negative: {greeks.vega}"


# ===========================================================================
# Brute-force grid (slow marker)
# ===========================================================================


@pytest.mark.slow
@pytest.mark.parametrize("p", _get_stress_grid(), ids=_param_id)
def test_bsm_stress_grid(p: PricingParams) -> None:
    """BSM must produce finite, non-negative prices for all stress inputs."""
    price = bsm_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(price), f"BSM price not finite: {price}"
    assert price >= -1e-10, f"BSM price negative: {price}"


@pytest.mark.slow
@pytest.mark.parametrize("p", _get_stress_grid(), ids=_param_id)
def test_american_stress_grid(p: PricingParams) -> None:
    """American must produce finite, non-negative prices for all stress inputs."""
    price = american_price(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(price), f"American price not finite: {price}"
    assert price >= -1e-10, f"American price negative: {price}"


@pytest.mark.slow
@pytest.mark.parametrize(
    "p",
    [p for p in _get_stress_grid() if p.T >= 0.003 and p.sigma >= 0.01],
    ids=_param_id,
)
def test_bsm_greeks_stress_grid(p: PricingParams) -> None:
    """BSM Greeks must be finite with delta in bounds for stress inputs."""
    greeks = bsm_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(greeks.delta), f"Delta not finite: {greeks.delta}"
    assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"
    assert math.isfinite(greeks.gamma), f"Gamma not finite: {greeks.gamma}"
    assert math.isfinite(greeks.theta), f"Theta not finite: {greeks.theta}"
    assert math.isfinite(greeks.vega), f"Vega not finite: {greeks.vega}"
    assert math.isfinite(greeks.rho), f"Rho not finite: {greeks.rho}"


@pytest.mark.slow
@pytest.mark.parametrize(
    "p",
    [p for p in _get_stress_grid() if p.T >= 0.003 and p.sigma >= 0.01],
    ids=_param_id,
)
def test_american_greeks_stress_grid(p: PricingParams) -> None:
    """American Greeks must be finite with delta in bounds for stress inputs."""
    greeks = american_greeks(p.S, p.K, p.T, p.r, p.q, p.sigma, p.option_type)
    assert math.isfinite(greeks.delta), f"Delta not finite: {greeks.delta}"
    assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"
    assert math.isfinite(greeks.gamma), f"Gamma not finite: {greeks.gamma}"
    assert math.isfinite(greeks.theta), f"Theta not finite: {greeks.theta}"
    assert math.isfinite(greeks.vega), f"Vega not finite: {greeks.vega}"
    assert math.isfinite(greeks.rho), f"Rho not finite: {greeks.rho}"
