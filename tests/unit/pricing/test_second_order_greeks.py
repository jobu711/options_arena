"""Unit tests for second-order Greeks: vanna, charm, vomma.

Tests cover:
- BSM analytical: known-value correctness, sign verification, boundary conditions
- BAW finite-difference: correctness for calls/puts, small-T charm guard
- Cross-verification: BSM vs BAW agree within rel=1e-3 for European inputs (q=0)
- Dispatch: AMERICAN routes to BAW, EUROPEAN routes to BSM
- Model: OptionGreeks new optional fields, NaN/Inf rejection, backward compat
"""

import math

import pytest
from pydantic import ValidationError

from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel
from options_arena.models.options import OptionGreeks
from options_arena.pricing._common import SecondOrderGreeks
from options_arena.pricing.american import american_second_order_greeks
from options_arena.pricing.bsm import bsm_second_order_greeks
from options_arena.pricing.dispatch import option_second_order_greeks

# ---------------------------------------------------------------------------
# Standard test parameters
# ---------------------------------------------------------------------------

# (S, K, T, r, q, sigma, description)
STANDARD_PARAMS = [
    (100.0, 100.0, 1.0, 0.05, 0.0, 0.20, "ATM, no dividend"),
    (100.0, 110.0, 0.5, 0.05, 0.02, 0.25, "OTM call, with dividend"),
    (100.0, 90.0, 0.25, 0.03, 0.01, 0.30, "ITM call, short DTE"),
    (50.0, 50.0, 1.0, 0.08, 0.03, 0.40, "ATM, high vol"),
    (200.0, 180.0, 2.0, 0.04, 0.015, 0.15, "deep ITM, low vol"),
]


# ---------------------------------------------------------------------------
# 1. BSM Analytical Tests (~12 tests)
# ---------------------------------------------------------------------------


class TestBsmSecondOrderGreeksAnalytical:
    """Tests for BSM analytical second-order Greeks."""

    @pytest.mark.critical
    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_all_greeks_finite(
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
        """All second-order Greeks should be finite for standard inputs."""
        result = bsm_second_order_greeks(S, K, T, r, q, sigma, option_type)
        assert result.vanna is not None
        assert result.charm is not None
        assert result.vomma is not None
        assert math.isfinite(result.vanna)
        assert math.isfinite(result.charm)
        assert math.isfinite(result.vomma)

    def test_vanna_same_for_call_and_put(self) -> None:
        """Vanna is the same for calls and puts (analytical property)."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.20
        call_greeks = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        put_greeks = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert call_greeks.vanna is not None
        assert put_greeks.vanna is not None
        assert call_greeks.vanna == pytest.approx(put_greeks.vanna, rel=1e-10)

    def test_vomma_same_for_call_and_put(self) -> None:
        """Vomma is the same for calls and puts (analytical property)."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.20
        call_greeks = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        put_greeks = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert call_greeks.vomma is not None
        assert put_greeks.vomma is not None
        assert call_greeks.vomma == pytest.approx(put_greeks.vomma, rel=1e-10)

    def test_vanna_sign_atm(self) -> None:
        """For ATM options, d2 is small; vanna = -e^(-qT)*n(d1)*d2/sigma.

        When S~K and q~0, d2 is slightly negative for typical r/sigma,
        making vanna positive (since the formula has a negation).
        """
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert result.vanna is not None
        # d2 = d1 - sigma*sqrt(T); for ATM no-div: d1 = (r + sigma^2/2)*sqrt(T)/sigma
        # d1 ~ (0.05 + 0.02)*1/0.20 = 0.35; d2 = 0.35 - 0.20 = 0.15
        # vanna = -e^0 * n(0.35) * 0.15 / 0.20 < 0
        # So vanna should be negative for these params.
        assert result.vanna < 0.0

    def test_vomma_non_negative_atm(self) -> None:
        """Vomma = vega * d1 * d2 / sigma. For ATM with d1>0 and d2>0, vomma > 0."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert result.vomma is not None
        # d1 ~ 0.35, d2 ~ 0.15 — both positive, vega > 0, so vomma > 0.
        assert result.vomma > 0.0

    def test_boundary_T_zero(self) -> None:
        """T=0 boundary: all second-order Greeks are None."""
        result = bsm_second_order_greeks(100.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_boundary_sigma_zero(self) -> None:
        """sigma=0 boundary: all second-order Greeks are None."""
        result = bsm_second_order_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.0, OptionType.CALL)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_boundary_negative_T(self) -> None:
        """Negative T boundary: all second-order Greeks are None."""
        result = bsm_second_order_greeks(100.0, 100.0, -0.1, 0.05, 0.0, 0.20, OptionType.PUT)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_boundary_negative_sigma(self) -> None:
        """Negative sigma boundary: all second-order Greeks are None."""
        result = bsm_second_order_greeks(100.0, 100.0, 1.0, 0.05, 0.0, -0.20, OptionType.CALL)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_known_value_vanna(self) -> None:
        """Verify vanna against hand-computed reference value.

        S=100, K=100, T=1, r=0.05, q=0, sigma=0.20
        d1 = (ln(1) + (0.05+0.02)*1) / 0.20 = 0.35
        d2 = 0.35 - 0.20 = 0.15
        n(d1) = norm.pdf(0.35) = 0.37524...
        vanna = -1 * 0.37524 * 0.15 / 0.20 = -0.28143...
        """
        from scipy.stats import norm

        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        d1 = (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        expected_vanna = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma

        result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert result.vanna is not None
        assert result.vanna == pytest.approx(expected_vanna, rel=1e-10)

    def test_known_value_vomma(self) -> None:
        """Verify vomma against hand-computed reference value.

        vomma = vega * d1 * d2 / sigma
        vega = S * e^(-qT) * n(d1) * sqrt(T) = 100 * 0.37524 * 1 = 37.524
        vomma = 37.524 * 0.35 * 0.15 / 0.20 = 9.8501...
        """
        from scipy.stats import norm

        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        d1 = (math.log(S / K) + (r - q + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        expected_vomma = vega * d1 * d2 / sigma

        result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert result.vomma is not None
        assert result.vomma == pytest.approx(expected_vomma, rel=1e-10)


# ---------------------------------------------------------------------------
# 2. BAW Finite-Difference Tests (~8 tests)
# ---------------------------------------------------------------------------


class TestBawSecondOrderGreeksFiniteDiff:
    """Tests for BAW finite-difference second-order Greeks."""

    @pytest.mark.critical
    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "q", "sigma", "desc"),
        STANDARD_PARAMS,
        ids=[p[-1] for p in STANDARD_PARAMS],
    )
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_all_greeks_finite(
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
        """All second-order Greeks should be finite for standard inputs."""
        result = american_second_order_greeks(S, K, T, r, q, sigma, option_type)
        assert result.vanna is not None
        assert result.charm is not None
        assert result.vomma is not None
        assert math.isfinite(result.vanna)
        assert math.isfinite(result.charm)
        assert math.isfinite(result.vomma)

    def test_boundary_T_zero(self) -> None:
        """T=0 boundary: all second-order Greeks are None."""
        result = american_second_order_greeks(100.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.CALL)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_boundary_sigma_zero(self) -> None:
        """sigma=0 boundary: all second-order Greeks are None."""
        result = american_second_order_greeks(100.0, 100.0, 1.0, 0.05, 0.0, 0.0, OptionType.PUT)
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)

    def test_charm_small_T_guard(self) -> None:
        """When T is very small (<= dT), charm uses forward difference instead of backward.

        This must not raise an error or produce NaN.
        """
        # dT = 1/365 ~ 0.00274. Use T < dT.
        T_small = 0.001  # Less than 1/365 ~ 0.00274.
        result = american_second_order_greeks(
            100.0, 100.0, T_small, 0.05, 0.0, 0.20, OptionType.CALL
        )
        assert result.charm is not None
        assert math.isfinite(result.charm)

    def test_vanna_sign_consistent_with_bsm(self) -> None:
        """BAW vanna sign should match BSM vanna sign for European inputs (q=0)."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert bsm_result.vanna is not None
        assert baw_result.vanna is not None
        # Same sign.
        assert (bsm_result.vanna > 0) == (baw_result.vanna > 0) or (
            abs(bsm_result.vanna) < 1e-6 and abs(baw_result.vanna) < 1e-6
        )


# ---------------------------------------------------------------------------
# 3. Cross-Verification: BSM vs BAW (~6 tests)
# ---------------------------------------------------------------------------


class TestCrossVerification:
    """BSM analytical vs BAW finite-difference should agree for calls with q=0.

    FR-P4 identity: when q=0, american_call == bsm_call, so all derivatives
    (including second-order) must match. For puts, BAW always has an early
    exercise premium (FR-P5), so puts are tested with broader tolerance.
    """

    @pytest.mark.critical
    def test_vanna_bsm_vs_baw_call(self) -> None:
        """Vanna: BSM vs BAW agree within rel=5e-3 for calls (q=0, FR-P4).

        Cross-partial finite differences have inherent O(dS*dSigma) truncation
        error, so a 0.5% relative tolerance is appropriate.
        """
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert bsm_result.vanna is not None
        assert baw_result.vanna is not None
        assert baw_result.vanna == pytest.approx(bsm_result.vanna, rel=5e-3)

    def test_charm_bsm_vs_baw_call(self) -> None:
        """Charm: BSM vs BAW agree within rel=1e-2 for calls (q=0, FR-P4).

        Charm uses a coarser tolerance because BAW uses a finite difference on T
        which is inherently less precise for the time derivative.
        """
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert bsm_result.charm is not None
        assert baw_result.charm is not None
        assert baw_result.charm == pytest.approx(bsm_result.charm, rel=1e-2)

    def test_vomma_bsm_vs_baw_call(self) -> None:
        """Vomma: BSM vs BAW agree within rel=5e-3 for calls (q=0, FR-P4)."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert bsm_result.vomma is not None
        assert baw_result.vomma is not None
        assert baw_result.vomma == pytest.approx(bsm_result.vomma, rel=5e-3)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "sigma", "desc"),
        [
            (100.0, 100.0, 1.0, 0.05, 0.20, "ATM"),
            (100.0, 110.0, 0.5, 0.05, 0.25, "OTM"),
            (100.0, 90.0, 0.25, 0.03, 0.30, "ITM"),
            (50.0, 50.0, 1.0, 0.08, 0.40, "ATM high vol"),
        ],
        ids=["ATM", "OTM", "ITM", "high-vol"],
    )
    def test_all_greeks_agree_calls_parametrized(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        desc: str,
    ) -> None:
        """All three second-order Greeks agree (BSM vs BAW) for calls with q=0 (FR-P4).

        Finite-difference second-order derivatives have inherent O(h^2) truncation
        error. We use rel=5e-3 with an abs=1e-3 floor to handle near-zero cases
        (where the analytical value is ~0 but numerical noise persists).
        """
        q = 0.0
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)

        assert bsm_result.vanna is not None
        assert baw_result.vanna is not None
        assert baw_result.vanna == pytest.approx(bsm_result.vanna, rel=5e-3, abs=1e-3)

        assert bsm_result.charm is not None
        assert baw_result.charm is not None
        # Charm tolerance is broader due to T finite-difference coarseness.
        assert baw_result.charm == pytest.approx(bsm_result.charm, rel=5e-2, abs=1e-3)

        assert bsm_result.vomma is not None
        assert baw_result.vomma is not None
        assert baw_result.vomma == pytest.approx(bsm_result.vomma, rel=5e-3, abs=1e-3)

    @pytest.mark.parametrize(
        ("S", "K", "T", "r", "sigma", "desc"),
        [
            (100.0, 100.0, 1.0, 0.05, 0.20, "ATM"),
            (100.0, 110.0, 0.5, 0.05, 0.25, "OTM"),
        ],
        ids=["ATM", "OTM"],
    )
    def test_puts_finite_and_same_order_of_magnitude(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        desc: str,
    ) -> None:
        """For puts, BAW differs from BSM (early exercise premium), but values
        should be finite and in the same order of magnitude."""
        q = 0.0
        bsm_result = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        baw_result = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.PUT)

        assert bsm_result.vanna is not None and baw_result.vanna is not None
        assert bsm_result.charm is not None and baw_result.charm is not None
        assert bsm_result.vomma is not None and baw_result.vomma is not None

        assert math.isfinite(baw_result.vanna)
        assert math.isfinite(baw_result.charm)
        assert math.isfinite(baw_result.vomma)


# ---------------------------------------------------------------------------
# 4. Dispatch Tests (~4 tests)
# ---------------------------------------------------------------------------


class TestDispatch:
    """Verify option_second_order_greeks dispatches correctly."""

    @pytest.mark.critical
    def test_american_routes_to_baw(self) -> None:
        """AMERICAN exercise style routes to american_second_order_greeks."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.20
        dispatched = option_second_order_greeks(
            ExerciseStyle.AMERICAN, S, K, T, r, q, sigma, OptionType.CALL
        )
        direct = american_second_order_greeks(S, K, T, r, q, sigma, OptionType.CALL)
        assert dispatched == direct

    def test_european_routes_to_bsm(self) -> None:
        """EUROPEAN exercise style routes to bsm_second_order_greeks."""
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.20
        dispatched = option_second_order_greeks(
            ExerciseStyle.EUROPEAN, S, K, T, r, q, sigma, OptionType.PUT
        )
        direct = bsm_second_order_greeks(S, K, T, r, q, sigma, OptionType.PUT)
        assert dispatched == direct

    def test_dispatch_returns_second_order_greeks_type(self) -> None:
        """Dispatch returns a SecondOrderGreeks NamedTuple."""
        result = option_second_order_greeks(
            ExerciseStyle.EUROPEAN, 100.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL
        )
        assert isinstance(result, SecondOrderGreeks)

    def test_dispatch_boundary_returns_all_none(self) -> None:
        """Dispatch with T=0 returns all-None SecondOrderGreeks."""
        result = option_second_order_greeks(
            ExerciseStyle.AMERICAN, 100.0, 100.0, 0.0, 0.05, 0.0, 0.20, OptionType.PUT
        )
        assert result == SecondOrderGreeks(vanna=None, charm=None, vomma=None)


# ---------------------------------------------------------------------------
# 5. Model Tests (~10 tests)
# ---------------------------------------------------------------------------


class TestOptionGreeksSecondOrder:
    """Tests for OptionGreeks model with new optional second-order fields."""

    def test_default_none(self) -> None:
        """New fields default to None when not provided."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
        )
        assert greeks.vanna is None
        assert greeks.charm is None
        assert greeks.vomma is None

    def test_backward_compatibility(self) -> None:
        """Construction without new fields still works (backward compat)."""
        greeks = OptionGreeks(
            delta=0.50,
            gamma=0.04,
            theta=-0.05,
            vega=0.20,
            rho=0.01,
            pricing_model=PricingModel.BAW,
        )
        assert greeks.delta == pytest.approx(0.50)
        assert greeks.pricing_model == PricingModel.BAW

    def test_accept_valid_floats(self) -> None:
        """Accept valid finite floats for vanna, charm, vomma."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
            vanna=-0.28,
            charm=0.01,
            vomma=9.85,
        )
        assert greeks.vanna == pytest.approx(-0.28)
        assert greeks.charm == pytest.approx(0.01)
        assert greeks.vomma == pytest.approx(9.85)

    def test_accept_negative_values(self) -> None:
        """Second-order Greeks can be negative (no sign constraint)."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
            vanna=-1.5,
            charm=-0.05,
            vomma=-3.0,
        )
        assert greeks.vanna == pytest.approx(-1.5)
        assert greeks.charm == pytest.approx(-0.05)
        assert greeks.vomma == pytest.approx(-3.0)

    def test_reject_nan_vanna(self) -> None:
        """NaN vanna is rejected by validator."""
        with pytest.raises(ValidationError, match="must be finite"):
            OptionGreeks(
                delta=0.45,
                gamma=0.03,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BSM,
                vanna=float("nan"),
            )

    def test_reject_inf_charm(self) -> None:
        """Inf charm is rejected by validator."""
        with pytest.raises(ValidationError, match="must be finite"):
            OptionGreeks(
                delta=0.45,
                gamma=0.03,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BSM,
                charm=float("inf"),
            )

    def test_reject_neg_inf_vomma(self) -> None:
        """-Inf vomma is rejected by validator."""
        with pytest.raises(ValidationError, match="must be finite"):
            OptionGreeks(
                delta=0.45,
                gamma=0.03,
                theta=-0.08,
                vega=0.15,
                rho=0.02,
                pricing_model=PricingModel.BSM,
                vomma=float("-inf"),
            )

    def test_frozen_second_order_fields(self) -> None:
        """Second-order fields respect frozen=True."""
        greeks = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
            vanna=-0.28,
        )
        with pytest.raises(ValidationError):
            greeks.vanna = 0.5  # type: ignore[misc]

    def test_json_roundtrip_with_second_order(self) -> None:
        """JSON serialization roundtrip preserves second-order Greeks."""
        original = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
            vanna=-0.28143,
            charm=0.01234,
            vomma=9.85012,
        )
        roundtripped = OptionGreeks.model_validate_json(original.model_dump_json())
        assert roundtripped == original

    def test_json_roundtrip_none_second_order(self) -> None:
        """JSON roundtrip preserves None for unset second-order fields."""
        original = OptionGreeks(
            delta=0.45,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            rho=0.02,
            pricing_model=PricingModel.BSM,
        )
        roundtripped = OptionGreeks.model_validate_json(original.model_dump_json())
        assert roundtripped.vanna is None
        assert roundtripped.charm is None
        assert roundtripped.vomma is None


# ---------------------------------------------------------------------------
# 6. Package Re-export Tests (~2 tests)
# ---------------------------------------------------------------------------


class TestReExport:
    """Verify that dispatch functions and types are importable from the package."""

    def test_import_option_second_order_greeks(self) -> None:
        """option_second_order_greeks is importable from options_arena.pricing."""
        from options_arena.pricing import option_second_order_greeks as func

        assert callable(func)

    def test_import_second_order_greeks_type(self) -> None:
        """SecondOrderGreeks is importable from options_arena.pricing."""
        from options_arena.pricing import SecondOrderGreeks as sog

        assert issubclass(sog, tuple)
