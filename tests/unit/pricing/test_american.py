"""Unit tests for BAW American option pricing: american_price, american_greeks, american_iv.

Tests cover:
- FR-P4 identity: american_call == bsm_call when q=0 (no early exercise for calls
  on non-dividend-paying stocks)
- FR-P5 dominance: american_put >= bsm_put always
- Early exercise premium: deep ITM puts show meaningful premium, premium monotonicity
- Reference values: non-negativity, intrinsic-value floor, sanity checks
- Greeks correctness: sign constraints, pricing_model=BAW, boundary values
- IV solver: round-trip convergence, error handling, custom PricingConfig
- Boundary conditions: T=0, deep ITM/OTM, q=0 cross-check
"""

import pytest

from options_arena.models.config import PricingConfig
from options_arena.models.enums import OptionType, PricingModel
from options_arena.pricing.american import american_greeks, american_iv, american_price
from options_arena.pricing.bsm import bsm_price

# ---------------------------------------------------------------------------
# Standard test parameters: (S, K, T, r, q, sigma)
# ---------------------------------------------------------------------------

STANDARD_PARAMS: list[tuple[float, float, float, float, float, float]] = [
    (100.0, 100.0, 1.0, 0.05, 0.02, 0.20),
    (100.0, 110.0, 0.5, 0.05, 0.03, 0.25),
    (100.0, 90.0, 0.25, 0.03, 0.01, 0.30),
    (50.0, 50.0, 1.0, 0.08, 0.03, 0.40),
    (200.0, 180.0, 2.0, 0.04, 0.015, 0.15),
    (100.0, 120.0, 1.0, 0.10, 0.05, 0.20),
]

STANDARD_IDS: list[str] = [
    "ATM-q0.02",
    "OTM-call-q0.03",
    "ITM-call-short-DTE",
    "ATM-high-vol",
    "deep-ITM-low-vol",
    "deep-ITM-put-high-r",
]


# ---------------------------------------------------------------------------
# 1. FR-P4 — Call identity when q=0 (~6 tests)
# ---------------------------------------------------------------------------


class TestFRP4CallIdentity:
    """When q=0, american_call == bsm_call exactly (no early exercise premium)."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "sigma"),
        [
            (100.0, 100.0, 1.0, 0.05, 0.20),
            (100.0, 110.0, 0.5, 0.08, 0.30),
            (50.0, 45.0, 0.25, 0.03, 0.25),
            (200.0, 200.0, 2.0, 0.04, 0.15),
            (100.0, 80.0, 1.0, 0.06, 0.35),
            (150.0, 160.0, 0.75, 0.05, 0.20),
        ],
        ids=[
            "ATM-1Y",
            "OTM-6M",
            "ITM-3M",
            "ATM-2Y",
            "deep-ITM-1Y",
            "OTM-9M",
        ],
    )
    def test_call_equals_bsm_when_no_dividend(
        self, S: float, K: float, T: float, r: float, sigma: float
    ) -> None:
        """American call with q=0 must equal BSM call (FR-P4 identity)."""
        q = 0.0
        bsm = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        baw = american_price(S, K, T, r, q, sigma, OptionType.CALL)
        assert baw == pytest.approx(bsm, rel=1e-6)


# ---------------------------------------------------------------------------
# 2. FR-P5 — Put dominance (~6 tests)
# ---------------------------------------------------------------------------


class TestFRP5PutDominance:
    """american_put >= bsm_put always (early exercise premium is non-negative)."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        STANDARD_PARAMS,
        ids=STANDARD_IDS,
    )
    def test_american_put_geq_bsm_put(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float
    ) -> None:
        """American put price must be >= BSM put price (FR-P5)."""
        bsm_put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        baw_put = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        # Small tolerance for float arithmetic.
        assert baw_put >= bsm_put - 1e-10


# ---------------------------------------------------------------------------
# 3. Early exercise premium (~4 tests)
# ---------------------------------------------------------------------------


class TestEarlyExercisePremium:
    """Tests for the magnitude and monotonicity of the early exercise premium."""

    def test_deep_itm_put_has_meaningful_premium(self) -> None:
        """Deep ITM put with dividends should have a non-trivial premium."""
        S, K, T, r, q, sigma = 80.0, 120.0, 1.0, 0.05, 0.02, 0.20
        bsm_put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        baw_put = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        premium = baw_put - bsm_put
        assert premium > 0.01, f"Expected meaningful premium, got {premium:.6f}"

    def test_premium_increases_with_higher_r(self) -> None:
        """Higher risk-free rate increases the early exercise premium for puts."""
        S, K, T, q, sigma = 90.0, 110.0, 1.0, 0.02, 0.20
        r_low, r_high = 0.02, 0.10
        bsm_put_low = bsm_price(S, K, T, r_low, q, sigma, OptionType.PUT)
        baw_put_low = american_price(S, K, T, r_low, q, sigma, OptionType.PUT)
        premium_low = baw_put_low - bsm_put_low

        bsm_put_high = bsm_price(S, K, T, r_high, q, sigma, OptionType.PUT)
        baw_put_high = american_price(S, K, T, r_high, q, sigma, OptionType.PUT)
        premium_high = baw_put_high - bsm_put_high

        assert premium_high > premium_low

    def test_premium_larger_for_deep_itm_than_atm(self) -> None:
        """Deep ITM puts should have a larger early exercise premium than ATM puts."""
        T, r, q, sigma = 1.0, 0.05, 0.02, 0.20

        # ATM
        S_atm, K_atm = 100.0, 100.0
        bsm_atm = bsm_price(S_atm, K_atm, T, r, q, sigma, OptionType.PUT)
        baw_atm = american_price(S_atm, K_atm, T, r, q, sigma, OptionType.PUT)
        premium_atm = baw_atm - bsm_atm

        # Deep ITM put
        S_itm, K_itm = 70.0, 100.0
        bsm_itm = bsm_price(S_itm, K_itm, T, r, q, sigma, OptionType.PUT)
        baw_itm = american_price(S_itm, K_itm, T, r, q, sigma, OptionType.PUT)
        premium_itm = baw_itm - bsm_itm

        assert premium_itm > premium_atm

    def test_deep_otm_put_near_zero_premium(self) -> None:
        """Deep OTM puts should have negligible early exercise premium."""
        S, K, T, r, q, sigma = 150.0, 100.0, 1.0, 0.05, 0.02, 0.20
        bsm_put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        baw_put = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        premium = baw_put - bsm_put
        # Very deep OTM — premium should be very small.
        assert premium < 0.05


# ---------------------------------------------------------------------------
# 4. Reference value sanity checks (~4 tests)
# ---------------------------------------------------------------------------


class TestReferenceValues:
    """Sanity checks: non-negativity, intrinsic floor, BSM spread for puts."""

    def test_american_put_exceeds_bsm_by_at_least_threshold(self) -> None:
        """ATM put with r=0.05, q=0.02, sigma=0.20: American > BSM by at least 0.10."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.20
        bsm_put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        baw_put = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        assert baw_put - bsm_put >= 0.10

    def test_call_identity_reference(self) -> None:
        """S=100, K=100, T=1.0, r=0.05, q=0.0, sigma=0.20: American call == BSM call."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        bsm_call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        baw_call = american_price(S, K, T, r, q, sigma, OptionType.CALL)
        assert baw_call == pytest.approx(bsm_call, rel=1e-6)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT], ids=["call", "put"])
    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        STANDARD_PARAMS,
        ids=STANDARD_IDS,
    )
    def test_prices_non_negative(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        q: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        """All American option prices must be non-negative."""
        price = american_price(S, K, T, r, q, sigma, option_type)
        assert price >= 0.0

    def test_american_put_geq_intrinsic(self) -> None:
        """American put price must be >= intrinsic value always."""
        S, K, T, r, q, sigma = 80.0, 100.0, 1.0, 0.05, 0.02, 0.20
        price = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        intrinsic = max(K - S, 0.0)
        assert price >= intrinsic - 1e-10


# ---------------------------------------------------------------------------
# 5. Greeks correctness (~10 tests)
# ---------------------------------------------------------------------------


class TestAmericanGreeks:
    """Tests for finite-difference Greeks: sign constraints, pricing_model, boundaries."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        STANDARD_PARAMS,
        ids=STANDARD_IDS,
    )
    def test_call_delta_in_zero_one(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float
    ) -> None:
        """Call delta must be in [0, 1]."""
        greeks = american_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert 0.0 <= greeks.delta <= 1.0

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        STANDARD_PARAMS,
        ids=STANDARD_IDS,
    )
    def test_put_delta_in_neg_one_zero(
        self, S: float, K: float, T: float, r: float, q: float, sigma: float
    ) -> None:
        """Put delta must be in [-1, 0]."""
        greeks = american_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert -1.0 <= greeks.delta <= 0.0

    def test_gamma_positive_call(self) -> None:
        """Gamma is non-negative for calls."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)
        assert greeks.gamma >= 0.0

    def test_gamma_positive_put(self) -> None:
        """Gamma is non-negative for puts."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.PUT)
        assert greeks.gamma >= 0.0

    def test_vega_positive_call(self) -> None:
        """Vega is non-negative for calls."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)
        assert greeks.vega >= 0.0

    def test_vega_positive_put(self) -> None:
        """Vega is non-negative for puts."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.PUT)
        assert greeks.vega >= 0.0

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT], ids=["call", "put"])
    def test_pricing_model_is_baw(self, option_type: OptionType) -> None:
        """Greeks pricing_model must be PricingModel.BAW."""
        greeks = american_greeks(100.0, 100.0, 1.0, 0.05, 0.02, 0.20, option_type)
        assert greeks.pricing_model == PricingModel.BAW

    def test_greeks_similar_to_bsm_for_otm_call(self) -> None:
        """OTM call: BAW Greeks should be in the same order of magnitude as BSM Greeks."""
        from options_arena.pricing.bsm import bsm_greeks

        S, K, T, r, q, sigma = 100.0, 120.0, 1.0, 0.05, 0.02, 0.20
        baw = american_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        bsm = bsm_greeks(S, K, T, r, q, sigma, OptionType.CALL)

        # Delta within a reasonable relative tolerance.
        assert baw.delta == pytest.approx(bsm.delta, rel=1e-1)
        # Gamma within order of magnitude.
        assert baw.gamma == pytest.approx(bsm.gamma, rel=0.5)

    def test_boundary_greeks_t_zero_deep_itm_call(self) -> None:
        """At T=0, deep ITM call: delta=1.0, gamma/vega/rho=0."""
        greeks = american_greeks(150.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.CALL)
        assert greeks.delta == pytest.approx(1.0)
        assert greeks.gamma == pytest.approx(0.0)
        assert greeks.vega == pytest.approx(0.0)
        assert greeks.rho == pytest.approx(0.0)
        assert greeks.pricing_model == PricingModel.BAW

    def test_boundary_greeks_t_zero_deep_itm_put(self) -> None:
        """At T=0, deep ITM put: delta=-1.0, gamma/vega/rho=0."""
        greeks = american_greeks(50.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.PUT)
        assert greeks.delta == pytest.approx(-1.0)
        assert greeks.gamma == pytest.approx(0.0)
        assert greeks.vega == pytest.approx(0.0)
        assert greeks.rho == pytest.approx(0.0)
        assert greeks.pricing_model == PricingModel.BAW


# ---------------------------------------------------------------------------
# 6. IV solver (~6 tests)
# ---------------------------------------------------------------------------


class TestAmericanIvSolver:
    """Tests for brentq-based IV solver: round-trips, convergence, error handling."""

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma"),
        [
            (100.0, 100.0, 1.0, 0.05, 0.02, 0.20),
            (100.0, 110.0, 0.5, 0.05, 0.03, 0.25),
            (50.0, 50.0, 1.0, 0.08, 0.03, 0.40),
        ],
        ids=["ATM", "OTM-call", "ATM-high-vol"],
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
        option_type: OptionType,
    ) -> None:
        """Compute price from sigma, recover sigma via IV solver, verify price matches."""
        price = american_price(S, K, T, r, q, sigma, option_type)
        recovered_sigma = american_iv(price, S, K, T, r, q, option_type)
        recovered_price = american_price(S, K, T, r, q, recovered_sigma, option_type)
        assert recovered_price == pytest.approx(price, rel=1e-4)

    def test_iv_raises_on_zero_market_price(self) -> None:
        """ValueError raised when market_price = 0."""
        with pytest.raises(ValueError, match="market_price must be > 0"):
            american_iv(0.0, 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_raises_on_negative_market_price(self) -> None:
        """ValueError raised when market_price < 0."""
        with pytest.raises(ValueError, match="market_price must be > 0"):
            american_iv(-5.0, 100.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_raises_on_zero_t(self) -> None:
        """ValueError raised when T = 0."""
        with pytest.raises(ValueError, match="T must be > 0"):
            american_iv(5.0, 100.0, 100.0, 0.0, 0.05, 0.0, OptionType.CALL)

    def test_iv_custom_config_tolerance(self) -> None:
        """IV solver respects custom PricingConfig with wider tolerance."""
        config = PricingConfig(iv_solver_tol=1e-3, iv_solver_max_iter=100)
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        price = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        recovered = american_iv(price, S, K, T, r, q, OptionType.PUT, config=config)
        recovered_price = american_price(S, K, T, r, q, recovered, OptionType.PUT)
        assert recovered_price == pytest.approx(price, abs=1e-2)

    def test_iv_convergence_within_maxiter(self) -> None:
        """IV solver converges within default maxiter for reasonable inputs."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.30
        price = american_price(S, K, T, r, q, sigma, OptionType.PUT)
        # Should not raise — convergence within 50 iterations.
        recovered = american_iv(price, S, K, T, r, q, OptionType.PUT)
        assert recovered == pytest.approx(sigma, rel=1e-3)


# ---------------------------------------------------------------------------
# 7. Boundary conditions (~4 tests)
# ---------------------------------------------------------------------------


class TestBoundaryConditions:
    """Tests for pricing behavior at boundary conditions: T=0, deep ITM/OTM."""

    def test_t_zero_returns_intrinsic_itm_call(self) -> None:
        """At expiration (T=0), ITM call returns intrinsic value S - K."""
        price = american_price(110.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.CALL)
        assert price == pytest.approx(10.0)

    def test_t_zero_returns_intrinsic_itm_put(self) -> None:
        """At expiration (T=0), ITM put returns intrinsic value K - S."""
        price = american_price(90.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.PUT)
        assert price == pytest.approx(10.0)

    def test_t_zero_returns_zero_otm_call(self) -> None:
        """At expiration (T=0), OTM call returns 0."""
        price = american_price(90.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.CALL)
        assert price == pytest.approx(0.0)

    def test_t_zero_returns_zero_otm_put(self) -> None:
        """At expiration (T=0), OTM put returns 0."""
        price = american_price(110.0, 100.0, 0.0, 0.05, 0.02, 0.20, OptionType.PUT)
        assert price == pytest.approx(0.0)

    def test_deep_itm_call_near_intrinsic(self) -> None:
        """Deep ITM call: price should be close to intrinsic S - K."""
        S, K, T, r, q, sigma = 200.0, 100.0, 0.25, 0.05, 0.02, 0.20
        price = american_price(S, K, T, r, q, sigma, OptionType.CALL)
        intrinsic = S - K
        # Deep ITM call approaches intrinsic (within a few percent).
        assert price >= intrinsic * 0.95

    def test_deep_otm_call_near_zero(self) -> None:
        """Deep OTM call: price should be near zero."""
        price = american_price(50.0, 200.0, 0.25, 0.05, 0.02, 0.20, OptionType.CALL)
        assert price < 0.01

    def test_sigma_zero_returns_intrinsic(self) -> None:
        """With sigma=0, price equals intrinsic value."""
        price = american_price(110.0, 100.0, 1.0, 0.05, 0.0, 0.0, OptionType.CALL)
        assert price == pytest.approx(10.0)

    def test_very_small_t_converges_to_intrinsic(self) -> None:
        """With very small T (near expiration), price converges toward intrinsic."""
        S, K = 110.0, 100.0
        T_small = 1.0 / 365.0  # 1 day
        price = american_price(S, K, T_small, 0.05, 0.02, 0.20, OptionType.CALL)
        intrinsic = max(S - K, 0.0)
        # Should be very close to intrinsic with 1 day to expiration.
        assert price == pytest.approx(intrinsic, rel=0.05)
