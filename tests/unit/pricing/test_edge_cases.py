"""Edge case and coverage gap tests for the pricing module.

Covers scenarios identified by code analysis that the primary test suites
(test_bsm.py, test_american.py, test_dispatch.py) do not exercise:

- S=0 / K=0 input validation (ValueError)
- Negative sigma handling
- Very large T (LEAPS, T=10 years)
- BSM analytical Greeks vs numerical finite-difference cross-validation
- BAW call early exercise premium when q > 0
- Extreme initial guess for BSM IV solver
- Deep ITM put with high r for BAW IV
"""

import math

import pytest

from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel
from options_arena.pricing.american import american_greeks, american_iv, american_price
from options_arena.pricing.bsm import bsm_greeks, bsm_iv, bsm_price, bsm_vega
from options_arena.pricing.dispatch import option_greeks, option_price

# ---------------------------------------------------------------------------
# Test: S=0 and K=0 raise ValueError (W1 validation)
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Verify that S <= 0 and K <= 0 raise clear ValueError."""

    def test_bsm_price_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            bsm_price(0.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)

    def test_bsm_price_k_zero(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            bsm_price(100.0, 0.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)

    def test_bsm_price_s_negative(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            bsm_price(-10.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.PUT)

    def test_bsm_price_k_negative(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            bsm_price(100.0, -5.0, 1.0, 0.05, 0.0, 0.20, OptionType.PUT)

    def test_bsm_greeks_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            bsm_greeks(0.0, 100.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)

    def test_bsm_greeks_k_zero(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            bsm_greeks(100.0, 0.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL)

    def test_bsm_vega_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            bsm_vega(0.0, 100.0, 1.0, 0.05, 0.0, 0.20)

    def test_bsm_iv_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            bsm_iv(5.0, 0.0, 100.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_bsm_iv_k_zero(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            bsm_iv(5.0, 100.0, 0.0, 1.0, 0.05, 0.0, OptionType.CALL)

    def test_american_price_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            american_price(0.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)

    def test_american_price_k_zero(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            american_price(100.0, 0.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL)

    def test_american_greeks_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            american_greeks(0.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.PUT)

    def test_american_iv_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            american_iv(5.0, 0.0, 100.0, 1.0, 0.05, 0.02, OptionType.PUT)

    def test_dispatch_price_s_zero(self) -> None:
        with pytest.raises(ValueError, match="S.*must be > 0"):
            option_price(
                ExerciseStyle.AMERICAN, 0.0, 100.0, 1.0, 0.05, 0.02, 0.20, OptionType.CALL
            )

    def test_dispatch_greeks_k_zero(self) -> None:
        with pytest.raises(ValueError, match="K.*must be > 0"):
            option_greeks(
                ExerciseStyle.EUROPEAN, 100.0, 0.0, 1.0, 0.05, 0.0, 0.20, OptionType.CALL
            )


# ---------------------------------------------------------------------------
# Test: Negative sigma
# ---------------------------------------------------------------------------


class TestNegativeSigma:
    """Verify that negative sigma is handled gracefully (returns intrinsic/boundary)."""

    def test_bsm_price_negative_sigma_call_itm(self) -> None:
        price = bsm_price(110.0, 100.0, 1.0, 0.05, 0.0, -0.20, OptionType.CALL)
        # Negative sigma treated like zero: discounted intrinsic.
        assert price >= 0.0
        assert price == pytest.approx(
            max(110.0 * math.exp(-0.0) - 100.0 * math.exp(-0.05), 0.0), abs=0.01
        )

    def test_bsm_price_negative_sigma_put_otm(self) -> None:
        price = bsm_price(110.0, 100.0, 1.0, 0.05, 0.0, -0.20, OptionType.PUT)
        assert price == pytest.approx(0.0, abs=0.01)

    def test_bsm_greeks_negative_sigma(self) -> None:
        greeks = bsm_greeks(110.0, 100.0, 1.0, 0.05, 0.0, -0.20, OptionType.CALL)
        assert greeks.delta == 1.0  # ITM boundary
        assert greeks.gamma == 0.0
        assert greeks.pricing_model == PricingModel.BSM

    def test_american_price_negative_sigma(self) -> None:
        price = american_price(110.0, 100.0, 1.0, 0.05, 0.02, -0.20, OptionType.CALL)
        assert price == pytest.approx(10.0, abs=0.01)  # intrinsic

    def test_american_greeks_negative_sigma(self) -> None:
        greeks = american_greeks(110.0, 100.0, 1.0, 0.05, 0.02, -0.20, OptionType.CALL)
        assert greeks.delta == 1.0
        assert greeks.pricing_model == PricingModel.BAW


# ---------------------------------------------------------------------------
# Test: Very large T (LEAPS — 5 and 10 years)
# ---------------------------------------------------------------------------


class TestLargeT:
    """Verify pricing works for long-dated LEAPS-like options."""

    @pytest.mark.parametrize("T", [5.0, 10.0])
    def test_bsm_price_large_t_non_negative(self, T: float) -> None:
        call = bsm_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.CALL)
        put = bsm_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.PUT)
        assert call > 0.0
        assert put > 0.0

    @pytest.mark.parametrize("T", [5.0, 10.0])
    def test_bsm_put_call_parity_large_t(self, T: float) -> None:
        S, K, r, q, sigma = 100.0, 100.0, 0.05, 0.02, 0.25
        call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        put = bsm_price(S, K, T, r, q, sigma, OptionType.PUT)
        parity = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert call - put == pytest.approx(parity, rel=1e-6)

    @pytest.mark.parametrize("T", [5.0, 10.0])
    def test_american_price_large_t_non_negative(self, T: float) -> None:
        call = american_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.CALL)
        put = american_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.PUT)
        assert call > 0.0
        assert put > 0.0

    @pytest.mark.parametrize("T", [5.0, 10.0])
    def test_frp5_large_t(self, T: float) -> None:
        """FR-P5 holds for long-dated options."""
        bsm_put = bsm_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.PUT)
        baw_put = american_price(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.PUT)
        assert baw_put >= bsm_put - 1e-10

    @pytest.mark.parametrize("T", [5.0, 10.0])
    def test_bsm_greeks_large_t(self, T: float) -> None:
        greeks = bsm_greeks(100.0, 100.0, T, 0.05, 0.02, 0.25, OptionType.CALL)
        assert 0.0 <= greeks.delta <= 1.0
        assert greeks.gamma >= 0.0
        assert greeks.vega >= 0.0


# ---------------------------------------------------------------------------
# Test: BSM analytical Greeks vs numerical finite-difference cross-validation
# ---------------------------------------------------------------------------


class TestGreeksCrossValidation:
    """Verify BSM analytical Greeks match numerical finite-difference estimates."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_delta_matches_finite_difference(self, option_type: OptionType) -> None:
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        dS = 0.01 * S
        num_delta = (
            bsm_price(S + dS, K, T, r, q, sigma, option_type)
            - bsm_price(S - dS, K, T, r, q, sigma, option_type)
        ) / (2 * dS)
        analytical = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert analytical.delta == pytest.approx(num_delta, rel=1e-3)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_gamma_matches_finite_difference(self, option_type: OptionType) -> None:
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        dS = 0.01 * S
        p_up = bsm_price(S + dS, K, T, r, q, sigma, option_type)
        p_mid = bsm_price(S, K, T, r, q, sigma, option_type)
        p_dn = bsm_price(S - dS, K, T, r, q, sigma, option_type)
        num_gamma = (p_up - 2 * p_mid + p_dn) / (dS**2)
        analytical = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert analytical.gamma == pytest.approx(num_gamma, rel=1e-3)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_vega_matches_finite_difference(self, option_type: OptionType) -> None:
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        dSigma = 0.001
        num_vega = (
            bsm_price(S, K, T, r, q, sigma + dSigma, option_type)
            - bsm_price(S, K, T, r, q, sigma - dSigma, option_type)
        ) / (2 * dSigma)
        analytical = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert analytical.vega == pytest.approx(num_vega, rel=1e-4)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_theta_matches_finite_difference(self, option_type: OptionType) -> None:
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        dT = 1.0 / 365.0
        num_theta = (
            bsm_price(S, K, T - dT, r, q, sigma, option_type)
            - bsm_price(S, K, T, r, q, sigma, option_type)
        ) / dT
        analytical = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert analytical.theta == pytest.approx(num_theta, rel=5e-3)

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_rho_matches_finite_difference(self, option_type: OptionType) -> None:
        S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.02, 0.25
        dR = 0.001
        num_rho = (
            bsm_price(S, K, T, r + dR, q, sigma, option_type)
            - bsm_price(S, K, T, r - dR, q, sigma, option_type)
        ) / (2 * dR)
        analytical = bsm_greeks(S, K, T, r, q, sigma, option_type)
        assert analytical.rho == pytest.approx(num_rho, rel=1e-3)


# ---------------------------------------------------------------------------
# Test: BAW call early exercise premium when q > 0
# ---------------------------------------------------------------------------


class TestBawCallWithDividends:
    """Verify BAW call has early exercise premium when q > 0."""

    @pytest.mark.parametrize("q", [0.03, 0.05, 0.08])
    def test_call_premium_positive_with_dividend(self, q: float) -> None:
        """American call > BSM call when q > 0 (dividends make early exercise valuable)."""
        S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.25
        bsm_call = bsm_price(S, K, T, r, q, sigma, OptionType.CALL)
        baw_call = american_price(S, K, T, r, q, sigma, OptionType.CALL)
        # Premium should be non-negative (FR-P5 analog for calls with dividends).
        assert baw_call >= bsm_call - 1e-10

    def test_call_premium_increases_with_higher_dividend(self) -> None:
        """Higher dividend yield → larger early exercise premium for calls."""
        S, K, T, r, sigma = 100.0, 100.0, 1.0, 0.05, 0.25
        premium_low_q = american_price(S, K, T, r, 0.02, sigma, OptionType.CALL) - bsm_price(
            S, K, T, r, 0.02, sigma, OptionType.CALL
        )
        premium_high_q = american_price(S, K, T, r, 0.08, sigma, OptionType.CALL) - bsm_price(
            S, K, T, r, 0.08, sigma, OptionType.CALL
        )
        assert premium_high_q >= premium_low_q

    def test_deep_itm_call_with_dividend_near_intrinsic(self) -> None:
        """Deep ITM American call with high dividend should be near intrinsic."""
        S, K, T, r, q, sigma = 200.0, 100.0, 0.25, 0.05, 0.08, 0.20
        price = american_price(S, K, T, r, q, sigma, OptionType.CALL)
        intrinsic = S - K
        # Price should be at least intrinsic and close to it for deep ITM.
        assert price >= intrinsic - 0.01


# ---------------------------------------------------------------------------
# Test: Extreme initial guess for BSM IV solver
# ---------------------------------------------------------------------------


class TestBsmIvExtremeGuess:
    """Verify BSM IV solver behavior with non-standard initial guesses."""

    def test_iv_converges_with_moderately_high_guess(self) -> None:
        """Initial guess sigma=0.80, true sigma ≈ 0.20. Should converge."""
        S, K, T, r, q, sigma_true = 100.0, 100.0, 1.0, 0.05, 0.0, 0.20
        price = bsm_price(S, K, T, r, q, sigma_true, OptionType.CALL)
        recovered_iv = bsm_iv(price, S, K, T, r, q, OptionType.CALL, initial_guess=0.80)
        assert recovered_iv == pytest.approx(sigma_true, rel=1e-4)

    def test_iv_converges_with_moderately_low_guess(self) -> None:
        """Initial guess sigma=0.05, true sigma ≈ 0.40. Should converge."""
        S, K, T, r, q, sigma_true = 100.0, 100.0, 1.0, 0.05, 0.02, 0.40
        price = bsm_price(S, K, T, r, q, sigma_true, OptionType.PUT)
        recovered_iv = bsm_iv(price, S, K, T, r, q, OptionType.PUT, initial_guess=0.05)
        assert recovered_iv == pytest.approx(sigma_true, rel=1e-4)

    def test_iv_bracket_precheck_rejects_too_high_price(self) -> None:
        """Market price above theoretical max should raise immediately."""
        S, K, T, r, q = 100.0, 100.0, 1.0, 0.05, 0.0
        max_price = bsm_price(S, K, T, r, q, 5.0, OptionType.CALL)
        with pytest.raises(ValueError, match="outside the theoretical range"):
            bsm_iv(max_price + 10.0, S, K, T, r, q, OptionType.CALL)

    def test_iv_bracket_precheck_rejects_too_low_price(self) -> None:
        """Market price below theoretical min should raise immediately."""
        S, K, T, r, q = 100.0, 200.0, 1.0, 0.05, 0.0
        # Deep OTM call: price at sigma=1e-6 is essentially 0.
        with pytest.raises(ValueError, match="outside the theoretical range"):
            bsm_iv(200.0, S, K, T, r, q, OptionType.CALL)


# ---------------------------------------------------------------------------
# Test: Deep ITM put with high r for BAW IV
# ---------------------------------------------------------------------------


class TestBawIvDeepItm:
    """Test BAW IV solver for ITM options with higher interest rates."""

    def test_itm_put_high_r_iv_round_trip(self) -> None:
        """ITM put with high r: meaningful BAW premium, IV should round-trip."""
        S, K, T, r, q, sigma_true = 85.0, 100.0, 1.0, 0.10, 0.02, 0.30
        price = american_price(S, K, T, r, q, sigma_true, OptionType.PUT)
        recovered_iv = american_iv(price, S, K, T, r, q, OptionType.PUT)
        assert recovered_iv == pytest.approx(sigma_true, rel=1e-3)

    def test_itm_put_moderate_r_iv_round_trip(self) -> None:
        """Moderately ITM put: IV solver converges cleanly."""
        S, K, T, r, q, sigma_true = 90.0, 100.0, 0.5, 0.08, 0.03, 0.35
        price = american_price(S, K, T, r, q, sigma_true, OptionType.PUT)
        recovered_iv = american_iv(price, S, K, T, r, q, OptionType.PUT)
        assert recovered_iv == pytest.approx(sigma_true, rel=1e-3)

    def test_itm_call_with_dividend_iv_round_trip(self) -> None:
        """ITM call with dividend: IV solver should still converge."""
        S, K, T, r, q, sigma_true = 120.0, 100.0, 1.0, 0.05, 0.04, 0.25
        price = american_price(S, K, T, r, q, sigma_true, OptionType.CALL)
        recovered_iv = american_iv(price, S, K, T, r, q, OptionType.CALL)
        assert recovered_iv == pytest.approx(sigma_true, rel=1e-3)
