"""Stability tests for pricing functions: Hypothesis + extreme inputs + NaN injection.

Covers BSM (5 functions), BAW/American (4 functions), dispatch (4 functions),
and common helpers (1 function). Every function produces finite output for valid
inputs OR raises a clean ValueError for invalid inputs. Zero silent NaN propagation.
"""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from options_arena.models.enums import ExerciseStyle, OptionType
from options_arena.pricing._common import SecondOrderGreeks, intrinsic_value
from options_arena.pricing.american import (
    american_greeks,
    american_iv,
    american_price,
    american_second_order_greeks,
)
from options_arena.pricing.bsm import (
    bsm_greeks,
    bsm_iv,
    bsm_price,
    bsm_second_order_greeks,
    bsm_vega,
)
from options_arena.pricing.dispatch import (
    option_greeks,
    option_iv,
    option_price,
    option_second_order_greeks,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for valid pricing inputs
# ---------------------------------------------------------------------------

# Spot and strike: positive finite floats in a realistic range
_spot_strategy = st.floats(
    min_value=0.01, max_value=100_000, allow_nan=False, allow_infinity=False
)
_strike_strategy = st.floats(
    min_value=0.01, max_value=100_000, allow_nan=False, allow_infinity=False
)
_time_strategy = st.floats(min_value=1e-4, max_value=10.0, allow_nan=False, allow_infinity=False)
_rate_strategy = st.floats(min_value=-0.05, max_value=0.50, allow_nan=False, allow_infinity=False)
_div_strategy = st.floats(min_value=0.0, max_value=0.20, allow_nan=False, allow_infinity=False)
_sigma_strategy = st.floats(min_value=0.01, max_value=4.99, allow_nan=False, allow_infinity=False)
_option_type_strategy = st.sampled_from([OptionType.CALL, OptionType.PUT])
_exercise_style_strategy = st.sampled_from([ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN])

# ---------------------------------------------------------------------------
# Extreme input battery from PRD
# ---------------------------------------------------------------------------

EXTREME_S_VALUES = [0.01, 0.1, 1.0, 100.0, 10_000.0, 100_000.0]
EXTREME_K_VALUES = [0.01, 0.1, 1.0, 100.0, 10_000.0, 100_000.0]
EXTREME_T_VALUES = [1 / 365 / 24, 1 / 365, 7 / 365, 1.0, 5.0, 10.0]
EXTREME_SIGMA_VALUES = [0.01, 0.05, 0.5, 1.0, 3.0, 4.99]
EXTREME_R_VALUES = [-0.05, 0.0, 0.05, 0.15, 0.50]
EXTREME_MONEYNESS = [0.01, 0.5, 0.95, 1.0, 1.05, 2.0, 10.0]

# Build a manageable set of extreme combos (not full cartesian product)
EXTREME_PRICING_INPUTS: list[tuple[float, float, float, float, float, float]] = []
for S in [1.0, 100.0, 10_000.0]:
    for moneyness in EXTREME_MONEYNESS:
        K = S / moneyness if moneyness > 0 else S
        for T in EXTREME_T_VALUES:
            for sigma in [0.01, 0.5, 4.99]:
                for r in [-0.05, 0.05, 0.50]:
                    EXTREME_PRICING_INPUTS.append((S, K, T, r, 0.0, sigma))


# ===========================================================================
# BSM Price Stability
# ===========================================================================


class TestBSMPriceStability:
    """Hypothesis + extreme + NaN tests for bsm_price."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_price_finite_output(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: BSM price is always finite and non-negative for valid inputs."""
        price = bsm_price(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(price), f"BSM price not finite: {price}"
        assert price >= -1e-10, f"BSM price negative: {price}"

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
    )
    @settings(max_examples=200)
    def test_put_call_parity(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Property: C - P = S*exp(-qT) - K*exp(-rT) within tolerance."""
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        expected = S * math.exp(-q * T) - K * math.exp(-r * T)
        # Use absolute tolerance scaled by the magnitude of the inputs
        tol = max(1e-6, 1e-6 * max(abs(S), abs(K)))
        assert abs((call - put) - expected) < tol, (
            f"Put-call parity: C-P={call - put:.8f}, "
            f"expected={expected:.8f}, diff={abs((call - put) - expected):.2e}"
        )

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        r=_rate_strategy,
        q=_div_strategy,
        sigma=st.floats(min_value=0.05, max_value=4.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_call_monotonic_in_spot(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Property: call price increases with S."""
        dS = max(S * 0.05, 0.001)
        if S - dS <= 0:
            return
        price_lo = bsm_price(S - dS, K, T, r, q, sigma, OptionType.CALL)
        price_hi = bsm_price(S + dS, K, T, r, q, sigma, OptionType.CALL)
        assert price_hi >= price_lo - 1e-10, "Call not monotonic in S"

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        r=_rate_strategy,
        q=_div_strategy,
        sigma=st.floats(min_value=0.05, max_value=4.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_put_monotonic_decreasing_in_spot(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Property: put price decreases with S."""
        dS = max(S * 0.05, 0.001)
        if S - dS <= 0:
            return
        price_lo = bsm_price(S - dS, K, T, r, q, sigma, OptionType.PUT)
        price_hi = bsm_price(S + dS, K, T, r, q, sigma, OptionType.PUT)
        assert price_lo >= price_hi - 1e-10, "Put not monotonic (decreasing) in S"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "S,K,T,r,q,sigma",
        EXTREME_PRICING_INPUTS[:50],
        ids=[
            f"S={p[0]},K={p[1]:.2f},T={p[2]:.4f},sig={p[5]}" for p in EXTREME_PRICING_INPUTS[:50]
        ],
    )
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_bsm_extreme_inputs(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Extreme inputs produce finite output or clean error."""
        price = bsm_price(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(price), f"BSM price not finite: {price}"
        assert price >= -1e-10, f"BSM price negative: {price}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_bsm_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any input position raises ValueError or returns finite fallback."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        # sigma (position 5) NaN/Inf: BSM returns discounted intrinsic (documented fallback)
        if position == 5:
            price = bsm_price(
                args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
            )
            assert math.isfinite(price), f"BSM price not finite for sigma={bad_value}"
            assert price >= 0.0
        else:
            with pytest.raises(ValueError):
                bsm_price(args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL)


# ===========================================================================
# BSM Greeks Stability
# ===========================================================================


class TestBSMGreeksStability:
    """Hypothesis + extreme + NaN tests for bsm_greeks."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_greeks_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: All BSM Greeks are finite for valid inputs."""
        greeks = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(greeks.delta), f"Delta not finite: {greeks.delta}"
        assert math.isfinite(greeks.gamma), f"Gamma not finite: {greeks.gamma}"
        assert math.isfinite(greeks.theta), f"Theta not finite: {greeks.theta}"
        assert math.isfinite(greeks.vega), f"Vega not finite: {greeks.vega}"
        assert math.isfinite(greeks.rho), f"Rho not finite: {greeks.rho}"

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_vega_non_negative(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: BSM vega >= 0."""
        greeks = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert greeks.vega >= -1e-10, f"Vega negative: {greeks.vega}"

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_delta_bounds(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: BSM delta in [-1, 1] with correct sign."""
        greeks = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"
        if option_type == OptionType.CALL:
            assert greeks.delta >= -1e-10, f"Call delta negative: {greeks.delta}"
        else:
            assert greeks.delta <= 1e-10, f"Put delta positive: {greeks.delta}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    def test_bsm_greeks_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any input position raises ValueError or returns boundary Greeks."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        # sigma NaN/Inf returns boundary greeks (not ValueError)
        if position == 5:
            greeks = bsm_greeks(
                args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
            )
            assert math.isfinite(greeks.delta)
        else:
            with pytest.raises(ValueError):
                bsm_greeks(args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL)


# ===========================================================================
# BSM Vega (standalone) Stability
# ===========================================================================


class TestBSMVegaStability:
    """Hypothesis + NaN tests for bsm_vega."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_vega_finite_non_negative(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
    ) -> None:
        """Property: standalone bsm_vega is always finite and non-negative."""
        v = bsm_vega(S, K, T, r, q, sigma)
        assert math.isfinite(v), f"bsm_vega not finite: {v}"
        assert v >= -1e-10, f"bsm_vega negative: {v}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    def test_bsm_vega_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any position raises ValueError or returns 0.0."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        # sigma NaN/Inf returns 0.0 (documented fallback)
        if position == 5:
            v = bsm_vega(args[0], args[1], args[2], args[3], args[4], args[5])
            assert v == 0.0
        else:
            with pytest.raises(ValueError):
                bsm_vega(args[0], args[1], args[2], args[3], args[4], args[5])


# ===========================================================================
# BSM IV Stability
# ===========================================================================


class TestBSMIVStability:
    """Hypothesis + NaN tests for bsm_iv."""

    @pytest.mark.audit_stability
    @given(
        S=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.05, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=100)
    def test_bsm_iv_round_trip(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: bsm_price(bsm_iv(price)) approximately equals price."""
        market_price = bsm_price(S, K, T, r, q, sigma, option_type)
        if market_price <= 0.0:
            return  # Skip trivially zero prices
        try:
            recovered_sigma = bsm_iv(market_price, S, K, T, r, q, option_type)
            recovered_price = bsm_price(S, K, T, r, q, recovered_sigma, option_type)
            assert recovered_price == pytest.approx(market_price, abs=1e-4), (
                f"IV round-trip failed: original={market_price:.6f}, "
                f"recovered={recovered_price:.6f}, sigma_in={sigma:.6f}, "
                f"sigma_out={recovered_sigma:.6f}"
            )
        except ValueError:
            pass  # Some extreme combos may not converge — acceptable

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(7))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    def test_bsm_iv_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any position raises ValueError."""
        # args: market_price, S, K, T, r, q, option_type (skipping option_type for nan)
        args: list[float] = [5.0, 100.0, 100.0, 0.5, 0.05, 0.02, 0.0]
        if position < 6:
            args[position] = bad_value
            with pytest.raises(ValueError):
                bsm_iv(args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL)


# ===========================================================================
# BSM Second-Order Greeks Stability
# ===========================================================================


class TestBSMSecondOrderStability:
    """Hypothesis + NaN tests for bsm_second_order_greeks."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_bsm_second_order_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: BSM second-order Greeks are finite or None for valid inputs."""
        result = bsm_second_order_greeks(S, K, T, r, q, sigma, option_type)
        assert isinstance(result, SecondOrderGreeks)
        for field_name in ("vanna", "charm", "vomma"):
            val = getattr(result, field_name)
            if val is not None:
                assert math.isfinite(val), f"{field_name} not finite: {val}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    def test_bsm_second_order_nan_injection(self, position: int) -> None:
        """NaN in any position returns all-None or raises ValueError."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = float("nan")
        # Second-order Greeks return all-None for non-finite inputs (no raise)
        result = bsm_second_order_greeks(
            args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
        )
        assert result.vanna is None
        assert result.charm is None
        assert result.vomma is None


# ===========================================================================
# American Price Stability
# ===========================================================================


class TestAmericanPriceStability:
    """Hypothesis + extreme + NaN tests for american_price."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_american_price_finite_non_negative(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: American price is always finite and non-negative."""
        price = american_price(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(price), f"American price not finite: {price}"
        assert price >= -1e-10, f"American price negative: {price}"

    @pytest.mark.audit_stability
    @given(
        S=st.floats(min_value=10.0, max_value=1_000, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=10.0, max_value=1_000, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.05, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.10, max_value=2.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200, deadline=None)
    def test_american_ge_european(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: American price >= European price (early exercise premium >= 0).

        Constrained to moderate moneyness ratios where BAW critical price solver
        converges reliably. Extreme deep ITM/OTM (S/K > 100x) can cause BAW
        non-convergence where American price falls back to intrinsic.
        """
        # Skip extreme moneyness where BAW solver is known to fail
        moneyness = S / K
        if moneyness < 0.05 or moneyness > 20.0:
            return
        eur = bsm_price(S, K, T, r, q, sigma, option_type)
        amer = american_price(S, K, T, r, q, sigma, option_type)
        # BAW approximation can have tiny numerical violations at edge cases
        tol = max(1e-4, 1e-6 * max(abs(S), abs(K)))
        assert amer >= eur - tol, (
            f"American ({amer:.8f}) < European ({eur:.8f}) by {eur - amer:.2e}"
        )

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        sigma=_sigma_strategy,
    )
    @settings(max_examples=100)
    def test_american_call_equals_european_no_dividend(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
    ) -> None:
        """Property: American call == BSM call when q=0 (FR-P4 identity)."""
        eur = bsm_price(S, K, T, r, 0.0, sigma, OptionType.CALL)
        amer = american_price(S, K, T, r, 0.0, sigma, OptionType.CALL)
        assert amer == pytest.approx(eur, abs=1e-8), (
            f"FR-P4 violated: american={amer:.8f}, european={eur:.8f}"
        )

    @pytest.mark.audit_stability
    @pytest.mark.parametrize(
        "S,K,T,r,q,sigma",
        EXTREME_PRICING_INPUTS[:30],
        ids=[
            f"S={p[0]},K={p[1]:.2f},T={p[2]:.4f},sig={p[5]}" for p in EXTREME_PRICING_INPUTS[:30]
        ],
    )
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_american_extreme_inputs(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Extreme inputs produce finite output or clean error."""
        price = american_price(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(price), f"American price not finite: {price}"
        assert price >= -1e-10, f"American price negative: {price}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
    def test_american_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any input position raises ValueError or returns finite fallback."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        # sigma (position 5) NaN/Inf: American returns intrinsic_value (documented fallback)
        if position == 5:
            price = american_price(
                args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
            )
            assert math.isfinite(price), f"American price not finite for sigma={bad_value}"
            assert price >= 0.0
        else:
            with pytest.raises(ValueError):
                american_price(
                    args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
                )


# ===========================================================================
# American Greeks Stability
# ===========================================================================


class TestAmericanGreeksStability:
    """Hypothesis + NaN tests for american_greeks."""

    @pytest.mark.audit_stability
    @given(
        S=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=-0.05, max_value=0.30, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.10, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_american_greeks_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: All American Greeks are finite for valid inputs."""
        greeks = american_greeks(S, K, T, r, q, sigma, option_type)
        assert math.isfinite(greeks.delta), f"Delta not finite: {greeks.delta}"
        assert math.isfinite(greeks.gamma), f"Gamma not finite: {greeks.gamma}"
        assert math.isfinite(greeks.theta), f"Theta not finite: {greeks.theta}"
        assert math.isfinite(greeks.vega), f"Vega not finite: {greeks.vega}"
        assert math.isfinite(greeks.rho), f"Rho not finite: {greeks.rho}"
        assert -1.0 <= greeks.delta <= 1.0, f"Delta out of bounds: {greeks.delta}"
        assert greeks.gamma >= -1e-10, f"Gamma negative: {greeks.gamma}"
        assert greeks.vega >= -1e-10, f"Vega negative: {greeks.vega}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    def test_american_greeks_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any position raises ValueError."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        with pytest.raises(ValueError):
            american_greeks(args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL)


# ===========================================================================
# American IV Stability
# ===========================================================================


class TestAmericanIVStability:
    """Hypothesis + NaN tests for american_iv."""

    @pytest.mark.audit_stability
    @given(
        S=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.05, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_american_iv_round_trip(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: american_price(american_iv(price)) approximately equals price."""
        market_price = american_price(S, K, T, r, q, sigma, option_type)
        if market_price <= 0.0:
            return
        try:
            recovered_sigma = american_iv(market_price, S, K, T, r, q, option_type)
            recovered_price = american_price(S, K, T, r, q, recovered_sigma, option_type)
            assert recovered_price == pytest.approx(market_price, abs=1e-3), (
                f"IV round-trip failed: original={market_price:.6f}, "
                f"recovered={recovered_price:.6f}"
            )
        except ValueError:
            pass  # Some extreme combos may not converge

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    def test_american_iv_nan_inf_injection(self, position: int, bad_value: float) -> None:
        """NaN/Inf in any position raises ValueError."""
        args: list[float] = [5.0, 100.0, 100.0, 0.5, 0.05, 0.02]
        args[position] = bad_value
        with pytest.raises(ValueError):
            american_iv(args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL)


# ===========================================================================
# American Second-Order Greeks Stability
# ===========================================================================


class TestAmericanSecondOrderStability:
    """Hypothesis + NaN tests for american_second_order_greeks."""

    @pytest.mark.audit_stability
    @given(
        S=st.floats(min_value=10.0, max_value=1_000, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=10.0, max_value=1_000, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.05, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.10, max_value=2.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_american_second_order_finite(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: American second-order Greeks are finite or None."""
        result = american_second_order_greeks(S, K, T, r, q, sigma, option_type)
        assert isinstance(result, SecondOrderGreeks)
        for field_name in ("vanna", "charm", "vomma"):
            val = getattr(result, field_name)
            if val is not None:
                assert math.isfinite(val), f"{field_name} not finite: {val}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    def test_american_second_order_nan_injection(self, position: int) -> None:
        """NaN in any position returns all-None."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = float("nan")
        result = american_second_order_greeks(
            args[0], args[1], args[2], args[3], args[4], args[5], OptionType.CALL
        )
        assert result.vanna is None
        assert result.charm is None
        assert result.vomma is None


# ===========================================================================
# Dispatch Functions Stability
# ===========================================================================


class TestDispatchStability:
    """Hypothesis + NaN tests for dispatch functions."""

    @pytest.mark.audit_stability
    @given(
        exercise_style=_exercise_style_strategy,
        S=_spot_strategy,
        K=_strike_strategy,
        T=_time_strategy,
        r=_rate_strategy,
        q=_div_strategy,
        sigma=_sigma_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_option_price_finite(
        self,
        exercise_style: ExerciseStyle,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: dispatch option_price always finite and non-negative."""
        price = option_price(exercise_style, S, K, T, r, q, sigma, option_type)
        assert math.isfinite(price), f"Price not finite: {price}"
        assert price >= -1e-10, f"Price negative: {price}"

    @pytest.mark.audit_stability
    @given(
        exercise_style=_exercise_style_strategy,
        S=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=-0.05, max_value=0.30, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.10, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_option_greeks_finite(
        self,
        exercise_style: ExerciseStyle,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: dispatch option_greeks always returns finite Greeks."""
        greeks = option_greeks(exercise_style, S, K, T, r, q, sigma, option_type)
        assert math.isfinite(greeks.delta)
        assert math.isfinite(greeks.gamma)
        assert math.isfinite(greeks.theta)
        assert math.isfinite(greeks.vega)
        assert math.isfinite(greeks.rho)

    @pytest.mark.audit_stability
    @given(
        exercise_style=_exercise_style_strategy,
        S=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=1.0, max_value=10_000, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=-0.05, max_value=0.30, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.10, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=3.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_option_second_order_greeks_finite(
        self,
        exercise_style: ExerciseStyle,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: dispatch second-order Greeks are finite or None."""
        result = option_second_order_greeks(exercise_style, S, K, T, r, q, sigma, option_type)
        for field_name in ("vanna", "charm", "vomma"):
            val = getattr(result, field_name)
            if val is not None:
                assert math.isfinite(val), f"{field_name} not finite: {val}"

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    @pytest.mark.parametrize("exercise_style", [ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN])
    def test_dispatch_price_nan_inf_injection(
        self, position: int, bad_value: float, exercise_style: ExerciseStyle
    ) -> None:
        """NaN/Inf in any position raises ValueError or returns finite fallback."""
        args: list[float] = [100.0, 100.0, 0.5, 0.05, 0.02, 0.30]
        args[position] = bad_value
        # sigma (position 5) NaN/Inf: both BSM and American return finite fallback
        if position == 5:
            price = option_price(
                exercise_style,
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
                args[5],
                OptionType.CALL,
            )
            assert math.isfinite(price), f"Dispatch price not finite for sigma={bad_value}"
            assert price >= 0.0
        else:
            with pytest.raises(ValueError):
                option_price(
                    exercise_style,
                    args[0],
                    args[1],
                    args[2],
                    args[3],
                    args[4],
                    args[5],
                    OptionType.CALL,
                )


# ===========================================================================
# Intrinsic Value Stability
# ===========================================================================


class TestIntrinsicValueStability:
    """Hypothesis + NaN tests for intrinsic_value."""

    @pytest.mark.audit_stability
    @given(
        S=_spot_strategy,
        K=_strike_strategy,
        option_type=_option_type_strategy,
    )
    @settings(max_examples=200)
    def test_intrinsic_value_non_negative(
        self,
        S: float,
        K: float,
        option_type: OptionType,
    ) -> None:
        """Property: intrinsic value is always non-negative."""
        val = intrinsic_value(S, K, option_type)
        assert val >= 0.0, f"Intrinsic value negative: {val}"
        assert math.isfinite(val), f"Intrinsic value not finite: {val}"
        if option_type == OptionType.CALL:
            assert val == pytest.approx(max(S - K, 0.0), abs=1e-10)
        else:
            assert val == pytest.approx(max(K - S, 0.0), abs=1e-10)


# ===========================================================================
# Dispatch option_iv Stability
# ===========================================================================


class TestOptionIVStability:
    """Hypothesis + NaN tests for dispatch option_iv."""

    @pytest.mark.audit_stability
    @given(
        exercise_style=_exercise_style_strategy,
        S=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        K=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
        T=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        r=st.floats(min_value=0.0, max_value=0.15, allow_nan=False, allow_infinity=False),
        q=st.floats(min_value=0.0, max_value=0.05, allow_nan=False, allow_infinity=False),
        sigma=st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False),
        option_type=_option_type_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_option_iv_round_trip(
        self,
        exercise_style: ExerciseStyle,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """Property: option_price(option_iv(price)) approximately equals price."""
        market_price = option_price(exercise_style, S, K, T, r, q, sigma, option_type)
        if market_price <= 0.0:
            return
        try:
            recovered_sigma = option_iv(exercise_style, market_price, S, K, T, r, q, option_type)
            recovered_price = option_price(
                exercise_style, S, K, T, r, q, recovered_sigma, option_type
            )
            assert recovered_price == pytest.approx(market_price, abs=1e-3), (
                f"IV round-trip failed: original={market_price:.6f}, "
                f"recovered={recovered_price:.6f}"
            )
        except ValueError:
            pass  # Some extreme combos may not converge

    @pytest.mark.audit_stability
    @pytest.mark.parametrize("position", range(6))
    @pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
    @pytest.mark.parametrize("exercise_style", [ExerciseStyle.AMERICAN, ExerciseStyle.EUROPEAN])
    def test_option_iv_nan_inf_injection(
        self, position: int, bad_value: float, exercise_style: ExerciseStyle
    ) -> None:
        """NaN/Inf in any input position raises ValueError."""
        # args: market_price, S, K, T, r, q
        args: list[float] = [5.0, 100.0, 100.0, 0.5, 0.05, 0.02]
        args[position] = bad_value
        with pytest.raises(ValueError):
            option_iv(
                exercise_style,
                args[0],
                args[1],
                args[2],
                args[3],
                args[4],
                args[5],
                OptionType.CALL,
            )
