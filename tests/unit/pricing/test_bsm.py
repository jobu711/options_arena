"""Unit tests for BSM European option pricing: bsm_price, bsm_greeks, bsm_vega, bsm_iv.

Tests cover:
- Pricing correctness: put-call parity, Hull-textbook reference values, ATM approximation
- Boundary conditions: T=0, sigma=0, deep ITM/OTM
- Greeks correctness: sign constraints, symmetries (gamma/vega same for call/put), pricing_model
- IV solver: round-trip convergence, error handling, custom PricingConfig
- Standalone vega: consistency with bsm_greeks, boundary behavior
"""

import math

import pytest

from options_arena.models.config import PricingConfig
from options_arena.models.enums import OptionType, PricingModel
from options_arena.pricing.bsm import bsm_greeks, bsm_iv, bsm_price, bsm_vega

# ---------------------------------------------------------------------------
# Standard test parameters
# ---------------------------------------------------------------------------

STANDARD_PARAMS = [
    # (S, K, T, r, q, sigma, description)
    (100.0, 100.0, 1.0, 0.05, 0.0, 0.20, "ATM, no dividend"),
    (100.0, 110.0, 0.5, 0.05, 0.02, 0.25, "OTM call, with dividend"),
    (100.0, 90.0, 0.25, 0.03, 0.01, 0.30, "ITM call, short DTE"),
    (50.0, 50.0, 1.0, 0.08, 0.03, 0.40, "ATM, high vol"),
    (200.0, 180.0, 2.0, 0.04, 0.015, 0.15, "deep ITM, low vol"),
]


# ---------------------------------------------------------------------------
# 1. Pricing correctness (~8 tests)
# ---------------------------------------------------------------------------


class TestBsmPricingCorrectness:
    """Tests for BSM pricing accuracy: parity, reference values, non-negativity."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    def test_put_call_parity(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float, desc: str
    ) -> None:
        """Put-call parity: C - P = S*e^(-qT) - K*e^(-rT)."""
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        parity_rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert call - put == pytest.approx(parity_rhs, rel=1e-6)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "expected_call", "expected_put"),
        [
            # Hull-textbook reference: ATM, no dividend, 1Y, 5% rate, 20% vol
            (100.0, 100.0, 1.0, 0.05, 0.0, 0.20, 10.4506, 5.5735),
        ],
        ids=["Hull ATM reference"],
    )
    @pytest.mark.critical
    def test_known_reference_values_hull(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        expected_call: float,
        expected_put: float,
    ) -> None:
        """BSM prices match Hull-textbook reference values (tight tolerance)."""
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        assert call == pytest.approx(expected_call, abs=0.01)
        assert put == pytest.approx(expected_put, abs=0.01)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "expected_call", "expected_put"),
        [
            # OTM call, with dividend: S=100, K=110, T=0.5, r=0.05, q=0.02, sigma=0.25
            # Verified via put-call parity: C - P = S*e^(-qT) - K*e^(-rT) = -8.279107
            (100.0, 110.0, 0.5, 0.05, 0.02, 0.25, 3.8598, 12.1389),
        ],
        ids=["OTM with dividend reference"],
    )
    def test_known_reference_values_with_dividend(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        expected_call: float,
        expected_put: float,
    ) -> None:
        """BSM prices match reference values for options with dividend yield."""
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        assert call == pytest.approx(expected_call, abs=0.01)
        assert put == pytest.approx(expected_put, abs=0.01)

    def test_atm_approximation(self) -> None:
        """ATM call approx 0.4 * S * sigma * sqrt(T) for small T, q=0, r near 0."""
        S, K = 100.0, 100.0
        T = 0.1  # ~36 days
        r = 0.001  # near zero
        q = 0.0
        sigma = 0.20
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        approx_value = 0.4 * S * sigma * math.sqrt(T)
        # This is a rough approximation, so use abs tolerance
        assert call == pytest.approx(approx_value, abs=0.5)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT], ids=["call", "put"])
    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    def test_prices_non_negative(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        desc: str,
        option_type: OptionType,
    ) -> None:
        """All BSM prices must be non-negative."""
        price = bsm_price(S, K, T, r, q, sigma, option_type)
        assert price >= 0.0


# ---------------------------------------------------------------------------
# 2. Boundary conditions (~8 tests)
# ---------------------------------------------------------------------------


class TestBsmBoundaryConditions:
    """Tests for BSM behavior at boundary conditions: T=0, sigma=0, deep ITM/OTM."""

    def test_t_zero_itm_call(self) -> None:
        """At expiration (T=0), ITM call returns intrinsic value S - K."""
        price = bsm_price(110.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert price == pytest.approx(10.0)

    def test_t_zero_otm_call(self) -> None:
        """At expiration (T=0), OTM call returns 0."""
        price = bsm_price(90.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert price == pytest.approx(0.0)

    def test_t_zero_itm_put(self) -> None:
        """At expiration (T=0), ITM put returns intrinsic value K - S."""
        price = bsm_price(90.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert price == pytest.approx(10.0)

    def test_t_zero_otm_put(self) -> None:
        """At expiration (T=0), OTM put returns 0."""
        price = bsm_price(110.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert price == pytest.approx(0.0)

    def test_sigma_zero_itm_call(self) -> None:
        """With sigma=0 and ITM call, price = discounted intrinsic value."""
        S, K, T, r, q = 110.0, 100.0, 1.0, 0.05, 0.0
        price = bsm_price(S, K, T, r, q, 0.0, OptionType.CALL)
        expected = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert price == pytest.approx(max(expected, 0.0), rel=1e-6)

    def test_sigma_zero_otm_call(self) -> None:
        """With sigma=0 and OTM call, price = 0."""
        price = bsm_price(90.0, 100.0, 1.0, 0.05, 0.0, 0.0, OptionType.CALL)
        assert price == pytest.approx(0.0)

    def test_deep_itm_call(self) -> None:
        """Deep ITM call price approaches S*e^(-qT) - K*e^(-rT)."""
        S, K, T, r, q, sigma = 200.0, 100.0, 1.0, 0.05, 0.0, 0.20
        price = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        lower_bound = S * math.exp(-q * T) - K * math.exp(-r * T)
        # Deep ITM call should be very close to discounted intrinsic
        assert price >= lower_bound * 0.99

    def test_deep_otm_call(self) -> None:
        """Deep OTM call price approaches 0."""
        price = bsm_price(50.0, 200.0, 0.25, 0.05, 0.0, 0.20, OptionType.CALL)
        assert price < 0.01


# ---------------------------------------------------------------------------
# 3. Greeks correctness (~12 tests)
# ---------------------------------------------------------------------------


class TestBsmGreeks:
    """Tests for BSM analytical Greeks: sign constraints, symmetries, boundary values."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    def test_call_delta_in_zero_one(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float, desc: str
    ) -> None:
        """Call delta must be in [0, 1]."""
        greeks = bsm_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert 0.0 <= greeks.delta <= 1.0

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    def test_put_delta_in_neg_one_zero(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float, desc: str
    ) -> None:
        """Put delta must be in [-1, 0]."""
        greeks = bsm_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert -1.0 <= greeks.delta <= 0.0

    def test_gamma_positive_call(self) -> None:
        """Gamma is positive for calls."""
        greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert greeks.gamma > 0.0

    def test_gamma_positive_put(self) -> None:
        """Gamma is positive for puts."""
        greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert greeks.gamma > 0.0

    def test_gamma_same_for_call_and_put(self) -> None:
        """Gamma is identical for call and put at the same strike/params."""
        call_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, OptionType.CALL)
        put_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, OptionType.PUT)
        assert call_greeks.gamma == pytest.approx(put_greeks.gamma, rel=1e-10)

    def test_vega_positive_call(self) -> None:
        """Vega is positive for calls."""
        greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert greeks.vega > 0.0

    def test_vega_positive_put(self) -> None:
        """Vega is positive for puts."""
        greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert greeks.vega > 0.0

    def test_vega_same_for_call_and_put(self) -> None:
        """Vega is identical for call and put at the same strike/params."""
        call_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, OptionType.CALL)
        put_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.25, OptionType.PUT)
        assert call_greeks.vega == pytest.approx(put_greeks.vega, rel=1e-10)

    def test_theta_negative_atm(self) -> None:
        """Theta is typically negative for ATM options (time decay)."""
        call_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert call_greeks.theta < 0.0

    def test_rho_sign_correctness(self) -> None:
        """Rho > 0 for calls, < 0 for puts."""
        call_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        put_greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert call_greeks.rho > 0.0
        assert put_greeks.rho < 0.0

    def test_pricing_model_is_bsm(self) -> None:
        """Greeks pricing_model is PricingModel.BSM."""
        greeks = bsm_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert greeks.pricing_model == PricingModel.BSM

    def test_boundary_greeks_t_zero_itm_call(self) -> None:
        """At T=0, ITM call: delta=1.0, gamma=0, theta=0, vega=0, rho=0."""
        greeks = bsm_greeks(110.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert greeks.delta == pytest.approx(1.0)
        assert greeks.gamma == pytest.approx(0.0)
        assert greeks.theta == pytest.approx(0.0)
        assert greeks.vega == pytest.approx(0.0)
        assert greeks.rho == pytest.approx(0.0)
        assert greeks.pricing_model == PricingModel.BSM

    def test_boundary_greeks_t_zero_otm_call(self) -> None:
        """At T=0, OTM call: delta=0, gamma=0, theta=0, vega=0, rho=0."""
        greeks = bsm_greeks(90.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert greeks.delta == pytest.approx(0.0)
        assert greeks.gamma == pytest.approx(0.0)

    def test_boundary_greeks_t_zero_itm_put(self) -> None:
        """At T=0, ITM put: delta=-1.0."""
        greeks = bsm_greeks(90.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert greeks.delta == pytest.approx(-1.0)
        assert greeks.gamma == pytest.approx(0.0)

    def test_boundary_greeks_t_zero_otm_put(self) -> None:
        """At T=0, OTM put: delta=0."""
        greeks = bsm_greeks(110.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.PUT)
        assert greeks.delta == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 4. IV solver (~8 tests)
# ---------------------------------------------------------------------------


class TestBsmIvSolver:
    """Tests for Newton-Raphson IV solver: round-trips, convergence, error handling."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT], ids=["call", "put"])
    def test_iv_round_trip(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        desc: str,
        option_type: OptionType,
    ) -> None:
        """Compute price from sigma, then recover sigma via IV solver (round-trip)."""
        price = bsm_price(S, K, T, r, q, sigma, option_type)
        recovered_sigma = bsm_iv(price, S, K, T, r, q, option_type)
        assert recovered_sigma == pytest.approx(sigma, rel=1e-4)

    def test_iv_convergence_default_guess(self) -> None:
        """IV solver converges with default initial_guess=0.30."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.40
        price = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        recovered = bsm_iv(price, S, K, T, r, q, OptionType.CALL)
        assert recovered == pytest.approx(sigma, rel=1e-4)

    def test_iv_convergence_yfinance_guess(self) -> None:
        """IV solver converges with yfinance-style initial_guess (e.g. 0.45)."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        price = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        recovered = bsm_iv(price, S, K, T, r, q, OptionType.CALL, initial_guess=0.45)
        assert recovered == pytest.approx(sigma, rel=1e-4)

    def test_iv_raises_on_zero_market_price(self) -> None:
        """ValueError raised when market_price = 0."""
        with pytest.raises(ValueError, match="market_price must be a finite number"):
            bsm_iv(0.0, 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_raises_on_negative_market_price(self) -> None:
        """ValueError raised when market_price < 0."""
        with pytest.raises(ValueError, match="market_price must be a finite number"):
            bsm_iv(-1.0, 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_raises_on_zero_t(self) -> None:
        """ValueError raised when T = 0."""
        with pytest.raises(ValueError, match="T must be > 0"):
            bsm_iv(5.0, 100.0, 100.0, 0.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_raises_on_negative_t(self) -> None:
        """ValueError raised when T < 0."""
        with pytest.raises(ValueError, match="T must be > 0"):
            bsm_iv(5.0, 100.0, 100.0, -0.1, 0.05, 0.0, OptionType.CALL)

    def test_iv_custom_config_tolerance(self) -> None:
        """IV solver respects custom PricingConfig with wider tolerance."""
        config = PricingConfig(iv_solver_tol=1e-3, iv_solver_max_iter=100)
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.25
        price = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        recovered = bsm_iv(price, S, K, T, r, q, OptionType.CALL, config=config)
        # With wider tolerance, should still converge to roughly correct value
        assert recovered == pytest.approx(sigma, abs=1e-2)

    def test_iv_round_trip_price_match(self) -> None:
        """Price computed from recovered IV matches the original market price."""
        S, K, T, r, q, sigma = 100.0, 105.0, 0.5, 0.05, 0.01, 0.30
        original_price = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        recovered_sigma = bsm_iv(original_price, S, K, T, r, q, OptionType.PUT)
        recovered_price = bsm_price(S, K, T, r, q, recovered_sigma, OptionType.PUT)
        assert recovered_price == pytest.approx(original_price, rel=1e-5)


# ---------------------------------------------------------------------------
# 5. Standalone vega (~4 tests)
# ---------------------------------------------------------------------------


class TestBsmVega:
    """Tests for standalone bsm_vega: consistency with bsm_greeks, boundary behavior."""

    def test_matches_greeks_vega_call(self) -> None:
        """Standalone bsm_vega matches vega from bsm_greeks for a call."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        standalone = bsm_vega(S, K, T, r, q, sigma)
        greeks = bsm_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert standalone == pytest.approx(greeks.vega, rel=1e-10)

    def test_matches_greeks_vega_put(self) -> None:
        """Standalone bsm_vega matches vega from bsm_greeks for a put.

        Vega is option-type-independent (same for call and put), so bsm_vega
        (which takes no option_type arg) should match the greeks vega for puts too.
        """
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        standalone = bsm_vega(S, K, T, r, q, sigma)
        greeks = bsm_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert standalone == pytest.approx(greeks.vega, rel=1e-10)

    def test_vega_positive_atm(self) -> None:
        """Standalone vega is positive for ATM options."""
        vega = bsm_vega(100.0, 100.0, 1.0, 0.05, 0.0, 0.20)
        assert vega > 0.0

    def test_vega_zero_at_t_zero(self) -> None:
        """Standalone vega returns 0.0 when T = 0."""
        vega = bsm_vega(100.0, 100.0, 0.0, 0.05, 0.0, 0.20)
        assert vega == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 6. NaN defense for q, r, T parameters
# ---------------------------------------------------------------------------


class TestBsmNanDefense:
    """NaN inputs for q, r, T must raise ValueError, not propagate silently."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_price_nan_q_raises(self, option_type: OptionType) -> None:
        """bsm_price raises ValueError when q is NaN."""
        with pytest.raises(ValueError, match="q must be a finite number"):
            bsm_price(100.0, 100.0, 1.0, 0.05, float("nan"), 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_price_nan_r_raises(self, option_type: OptionType) -> None:
        """bsm_price raises ValueError when r is NaN."""
        with pytest.raises(ValueError, match="r must be a finite number"):
            bsm_price(100.0, 100.0, 1.0, float("nan"), 0.0, 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_price_nan_t_raises(self, option_type: OptionType) -> None:
        """bsm_price raises ValueError when T is NaN."""
        with pytest.raises(ValueError, match="T must be a finite number"):
            bsm_price(100.0, 100.0, float("nan"), 0.05, 0.0, 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_price_inf_q_raises(self, option_type: OptionType) -> None:
        """bsm_price raises ValueError when q is Inf."""
        with pytest.raises(ValueError, match="q must be a finite number"):
            bsm_price(100.0, 100.0, 1.0, 0.05, float("inf"), 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_greeks_nan_q_raises(self, option_type: OptionType) -> None:
        """bsm_greeks raises ValueError when q is NaN."""
        with pytest.raises(ValueError, match="q must be a finite number"):
            bsm_greeks(100.0, 100.0, 1.0, 0.05, float("nan"), 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_greeks_nan_r_raises(self, option_type: OptionType) -> None:
        """bsm_greeks raises ValueError when r is NaN."""
        with pytest.raises(ValueError, match="r must be a finite number"):
            bsm_greeks(100.0, 100.0, 1.0, float("nan"), 0.0, 0.20, option_type)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_greeks_nan_t_raises(self, option_type: OptionType) -> None:
        """bsm_greeks raises ValueError when T is NaN."""
        with pytest.raises(ValueError, match="T must be a finite number"):
            bsm_greeks(100.0, 100.0, float("nan"), 0.05, 0.0, 0.20, option_type)

    def test_vega_nan_q_raises(self) -> None:
        """bsm_vega raises ValueError when q is NaN."""
        with pytest.raises(ValueError, match="q must be a finite number"):
            bsm_vega(100.0, 100.0, 1.0, 0.05, float("nan"), 0.20)

    def test_vega_nan_r_raises(self) -> None:
        """bsm_vega raises ValueError when r is NaN."""
        with pytest.raises(ValueError, match="r must be a finite number"):
            bsm_vega(100.0, 100.0, 1.0, float("nan"), 0.0, 0.20)

    def test_vega_nan_t_raises(self) -> None:
        """bsm_vega raises ValueError when T is NaN."""
        with pytest.raises(ValueError, match="T must be a finite number"):
            bsm_vega(100.0, 100.0, float("nan"), 0.05, 0.0, 0.20)

    def test_iv_nan_q_raises(self) -> None:
        """bsm_iv raises ValueError when q is NaN."""
        with pytest.raises(ValueError, match="q must be a finite number"):
            bsm_iv(10.0, 100.0, 100.0, 1.0, 0.05, float("nan"), OptionType.CALL)

    def test_iv_nan_r_raises(self) -> None:
        """bsm_iv raises ValueError when r is NaN."""
        with pytest.raises(ValueError, match="r must be a finite number"):
            bsm_iv(10.0, 100.0, 100.0, 1.0, float("nan"), 0.0, OptionType.CALL)

    def test_iv_nan_t_raises(self) -> None:
        """bsm_iv raises ValueError when T is NaN."""
        with pytest.raises(ValueError, match="T must be a finite number"):
            bsm_iv(10.0, 100.0, 100.0, float("nan"), 0.05, 0.0, OptionType.CALL)

    def test_iv_nan_market_price_raises(self) -> None:
        """bsm_iv raises ValueError when market_price is NaN."""
        with pytest.raises(ValueError, match="market_price must be a finite number"):
            bsm_iv(float("nan"), 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_inf_market_price_raises(self) -> None:
        """bsm_iv raises ValueError when market_price is Inf."""
        with pytest.raises(ValueError, match="market_price must be a finite number"):
            bsm_iv(float("inf"), 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)
