"""Unit tests for the pricing dispatch layer: option_price, option_greeks, option_iv.

Tests cover:
- Routing correctness: AMERICAN -> BAW, EUROPEAN -> BSM (exact match)
- Greeks metadata: pricing_model set correctly per exercise style
- Config handling: explicit PricingConfig, None defaults, custom tolerance
- Package re-exports: dispatch functions importable from options_arena.pricing
- Cross-model consistency: FR-P4 and FR-P5 verified through the dispatch layer
"""

import pytest

from options_arena.models.config import PricingConfig
from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel
from options_arena.pricing.american import american_greeks, american_iv, american_price
from options_arena.pricing.bsm import bsm_greeks, bsm_iv, bsm_price
from options_arena.pricing.dispatch import option_greeks, option_iv, option_price

# ---------------------------------------------------------------------------
# Standard test parameters: S=100, K=100, T=1.0, r=0.05, q=0.02, sigma=0.20
# ---------------------------------------------------------------------------

STD_S: float = 100.0
STD_K: float = 100.0
STD_T: float = 1.0
STD_R: float = 0.05
STD_Q: float = 0.02
STD_SIGMA: float = 0.20


# ---------------------------------------------------------------------------
# 1. Routing correctness (~6 tests)
# ---------------------------------------------------------------------------


class TestRoutingCorrectness:
    """Verify dispatch routes to the correct engine and returns identical results."""

    def test_price_american_matches_american_price(self) -> None:
        """option_price(AMERICAN, ...) returns exactly american_price(...)."""
        dispatched = option_price(
            ExerciseStyle.AMERICAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        direct = american_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL)
        assert dispatched == direct

    def test_price_european_matches_bsm_price(self) -> None:
        """option_price(EUROPEAN, ...) returns exactly bsm_price(...)."""
        dispatched = option_price(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        direct = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        assert dispatched == direct

    def test_greeks_american_matches_american_greeks(self) -> None:
        """option_greeks(AMERICAN, ...) matches american_greeks(...) field-by-field."""
        dispatched = option_greeks(
            ExerciseStyle.AMERICAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        direct = american_greeks(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL)
        assert dispatched.delta == direct.delta
        assert dispatched.gamma == direct.gamma
        assert dispatched.theta == direct.theta
        assert dispatched.vega == direct.vega
        assert dispatched.rho == direct.rho
        assert dispatched.pricing_model == direct.pricing_model

    def test_greeks_european_matches_bsm_greeks(self) -> None:
        """option_greeks(EUROPEAN, ...) matches bsm_greeks(...) field-by-field."""
        dispatched = option_greeks(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        direct = bsm_greeks(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        assert dispatched.delta == direct.delta
        assert dispatched.gamma == direct.gamma
        assert dispatched.theta == direct.theta
        assert dispatched.vega == direct.vega
        assert dispatched.rho == direct.rho
        assert dispatched.pricing_model == direct.pricing_model

    def test_iv_american_matches_american_iv(self) -> None:
        """option_iv(AMERICAN, ...) matches american_iv(...) within IV tolerance."""
        market_price = american_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        dispatched = option_iv(
            ExerciseStyle.AMERICAN, market_price, STD_S, STD_K, STD_T, STD_R, STD_Q, OptionType.PUT
        )
        direct = american_iv(market_price, STD_S, STD_K, STD_T, STD_R, STD_Q, OptionType.PUT)
        assert dispatched == pytest.approx(direct, rel=1e-4)

    def test_iv_european_matches_bsm_iv(self) -> None:
        """option_iv(EUROPEAN, ...) matches bsm_iv(...) within IV tolerance."""
        market_price = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL)
        dispatched = option_iv(
            ExerciseStyle.EUROPEAN,
            market_price,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            OptionType.CALL,
        )
        direct = bsm_iv(market_price, STD_S, STD_K, STD_T, STD_R, STD_Q, OptionType.CALL)
        assert dispatched == pytest.approx(direct, rel=1e-4)


# ---------------------------------------------------------------------------
# 2. Greeks metadata (~4 tests)
# ---------------------------------------------------------------------------


class TestGreeksMetadata:
    """Verify pricing_model is set correctly on dispatched OptionGreeks."""

    def test_american_call_pricing_model_is_baw(self) -> None:
        """AMERICAN call -> pricing_model == PricingModel.BAW."""
        greeks = option_greeks(
            ExerciseStyle.AMERICAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        assert greeks.pricing_model == PricingModel.BAW

    def test_american_put_pricing_model_is_baw(self) -> None:
        """AMERICAN put -> pricing_model == PricingModel.BAW."""
        greeks = option_greeks(
            ExerciseStyle.AMERICAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        assert greeks.pricing_model == PricingModel.BAW

    def test_european_call_pricing_model_is_bsm(self) -> None:
        """EUROPEAN call -> pricing_model == PricingModel.BSM."""
        greeks = option_greeks(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        assert greeks.pricing_model == PricingModel.BSM

    def test_european_put_pricing_model_is_bsm(self) -> None:
        """EUROPEAN put -> pricing_model == PricingModel.BSM."""
        greeks = option_greeks(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        assert greeks.pricing_model == PricingModel.BSM


# ---------------------------------------------------------------------------
# 3. Config handling (~4 tests)
# ---------------------------------------------------------------------------


class TestConfigHandling:
    """Verify option_iv respects PricingConfig (explicit, None, custom tolerance)."""

    def test_iv_with_explicit_default_config(self) -> None:
        """option_iv with explicit PricingConfig() converges correctly."""
        config = PricingConfig()
        market_price = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL)
        recovered = option_iv(
            ExerciseStyle.EUROPEAN,
            market_price,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            OptionType.CALL,
            config=config,
        )
        assert recovered == pytest.approx(STD_SIGMA, rel=1e-4)

    def test_iv_with_none_config_uses_defaults(self) -> None:
        """option_iv with config=None should still converge (uses PricingConfig defaults)."""
        market_price = american_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        recovered = option_iv(
            ExerciseStyle.AMERICAN,
            market_price,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            OptionType.PUT,
            config=None,
        )
        # Recovered IV should reproduce a price close to the original.
        recovered_price = american_price(
            STD_S, STD_K, STD_T, STD_R, STD_Q, recovered, OptionType.PUT
        )
        assert recovered_price == pytest.approx(market_price, rel=1e-4)

    def test_iv_with_custom_tolerance(self) -> None:
        """option_iv with custom iv_solver_tol=1e-4 still converges."""
        config = PricingConfig(iv_solver_tol=1e-4)
        market_price = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        recovered = option_iv(
            ExerciseStyle.EUROPEAN,
            market_price,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            OptionType.PUT,
            config=config,
        )
        assert recovered == pytest.approx(STD_SIGMA, abs=1e-2)

    def test_iv_american_respects_config(self) -> None:
        """AMERICAN style also respects custom PricingConfig."""
        config = PricingConfig(iv_solver_tol=1e-3, iv_solver_max_iter=100)
        market_price = american_price(
            STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        recovered = option_iv(
            ExerciseStyle.AMERICAN,
            market_price,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            STD_Q,
            OptionType.CALL,
            config=config,
        )
        recovered_price = american_price(
            STD_S, STD_K, STD_T, STD_R, STD_Q, recovered, OptionType.CALL
        )
        assert recovered_price == pytest.approx(market_price, abs=1e-2)


# ---------------------------------------------------------------------------
# 4. Package re-exports (~3 tests)
# ---------------------------------------------------------------------------


class TestPackageReExports:
    """Verify dispatch functions are importable from options_arena.pricing."""

    def test_import_option_price(self) -> None:
        """option_price is importable from options_arena.pricing and callable."""
        from options_arena.pricing import option_price as op

        assert callable(op)

    def test_import_option_greeks(self) -> None:
        """option_greeks is importable from options_arena.pricing and callable."""
        from options_arena.pricing import option_greeks as og

        assert callable(og)

    def test_import_option_iv(self) -> None:
        """option_iv is importable from options_arena.pricing and callable."""
        from options_arena.pricing import option_iv as oi

        assert callable(oi)


# ---------------------------------------------------------------------------
# 5. Cross-model consistency (~3 tests)
# ---------------------------------------------------------------------------


class TestCrossModelConsistency:
    """Verify cross-model invariants via the dispatch layer (FR-P4, FR-P5)."""

    def test_european_dispatch_equals_bsm_exactly(self) -> None:
        """For European style, dispatch result == direct BSM result (exact equality)."""
        dispatched_call = option_price(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL
        )
        direct_call = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.CALL)
        assert dispatched_call == direct_call

        dispatched_put = option_price(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        direct_put = bsm_price(STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT)
        assert dispatched_put == direct_put

    def test_frp4_via_dispatch_call_q_zero(self) -> None:
        """FR-P4 via dispatch: American call with q=0 matches BSM call (no early exercise)."""
        q_zero = 0.0
        american_dispatched = option_price(
            ExerciseStyle.AMERICAN,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
        )
        european_dispatched = option_price(
            ExerciseStyle.EUROPEAN,
            STD_S,
            STD_K,
            STD_T,
            STD_R,
            q_zero,
            STD_SIGMA,
            OptionType.CALL,
        )
        assert american_dispatched == pytest.approx(european_dispatched, rel=1e-6)

    def test_frp5_via_dispatch_put_geq_bsm(self) -> None:
        """FR-P5 via dispatch: American put >= BSM put (early exercise premium non-negative)."""
        american_put = option_price(
            ExerciseStyle.AMERICAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        european_put = option_price(
            ExerciseStyle.EUROPEAN, STD_S, STD_K, STD_T, STD_R, STD_Q, STD_SIGMA, OptionType.PUT
        )
        assert american_put >= european_put - 1e-10
