"""Tests for aggregate_spread_greeks in pricing/spreads.py.

Covers: bull call spread, bear put spread, iron condor (4-leg), straddle,
short leg negation, quantity multiplier, missing Greeks, empty legs,
second-order aggregation, pricing model propagation, gamma sign for
long-only, delta clamping, and single-leg cases.
"""

from __future__ import annotations

import logging

import pytest

from options_arena.models.enums import OptionType, PositionSide, PricingModel
from options_arena.models.options import OptionGreeks, SpreadLeg
from options_arena.pricing.spreads import aggregate_spread_greeks
from tests.factories import make_option_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _greeks(
    *,
    delta: float = 0.5,
    gamma: float = 0.05,
    theta: float = -0.03,
    vega: float = 0.20,
    rho: float = 0.01,
    pricing_model: PricingModel = PricingModel.BAW,
    vanna: float | None = None,
    charm: float | None = None,
    vomma: float | None = None,
) -> OptionGreeks:
    """Shorthand to build an OptionGreeks with optional second-order."""
    return OptionGreeks(
        delta=delta,
        gamma=gamma,
        theta=theta,
        vega=vega,
        rho=rho,
        pricing_model=pricing_model,
        vanna=vanna,
        charm=charm,
        vomma=vomma,
    )


def _leg(
    greeks: OptionGreeks | None,
    side: PositionSide,
    quantity: int = 1,
    option_type: OptionType = OptionType.CALL,
) -> SpreadLeg:
    """Build a SpreadLeg with the given greeks, side, and quantity."""
    contract = make_option_contract(
        option_type=option_type,
        greeks=greeks,
    )
    return SpreadLeg(contract=contract, side=side, quantity=quantity)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAggregateSpreadGreeks:
    """Tests for aggregate_spread_greeks."""

    def test_bull_call_spread_greeks(self) -> None:
        """Long call + short call: net delta < long call delta."""
        long_call = _leg(
            _greeks(delta=0.60, gamma=0.04, theta=-0.05, vega=0.25, rho=0.02),
            PositionSide.LONG,
        )
        short_call = _leg(
            _greeks(delta=0.30, gamma=0.03, theta=-0.03, vega=0.15, rho=0.01),
            PositionSide.SHORT,
        )
        result = aggregate_spread_greeks([long_call, short_call])

        assert result is not None
        assert result.delta == pytest.approx(0.30, rel=1e-6)  # 0.60 - 0.30
        assert result.gamma == pytest.approx(0.01, rel=1e-6)  # 0.04 - 0.03
        assert result.theta == pytest.approx(-0.02, rel=1e-4)  # -0.05 - (-0.03)
        assert result.vega == pytest.approx(0.10, rel=1e-6)  # 0.25 - 0.15
        assert result.rho == pytest.approx(0.01, rel=1e-6)  # 0.02 - 0.01

    def test_bear_put_spread_greeks(self) -> None:
        """Long put + short put: net delta negative (bearish)."""
        long_put = _leg(
            _greeks(delta=-0.50, gamma=0.04, theta=-0.04, vega=0.20, rho=-0.02),
            PositionSide.LONG,
            option_type=OptionType.PUT,
        )
        short_put = _leg(
            _greeks(delta=-0.25, gamma=0.03, theta=-0.02, vega=0.12, rho=-0.01),
            PositionSide.SHORT,
            option_type=OptionType.PUT,
        )
        result = aggregate_spread_greeks([long_put, short_put])

        assert result is not None
        # Long: -0.50, Short negated: -(-0.25) = +0.25 => net = -0.25
        assert result.delta == pytest.approx(-0.25, rel=1e-6)
        # Long: 0.04, Short negated: -(0.03) = -0.03 => net = 0.01
        assert result.gamma == pytest.approx(0.01, rel=1e-6)
        # Long: -0.04, Short negated: -(-0.02) = +0.02 => net = -0.02
        assert result.theta == pytest.approx(-0.02, rel=1e-4)
        # Long: 0.20, Short negated: -(0.12) = -0.12 => net = 0.08
        assert result.vega == pytest.approx(0.08, rel=1e-6)

    def test_iron_condor_four_legs(self) -> None:
        """4-leg iron condor: partial cancellation across legs."""
        # Bear call spread (short call lower + long call higher)
        short_call = _leg(
            _greeks(delta=0.30, gamma=0.03, theta=-0.03, vega=0.15, rho=0.01),
            PositionSide.SHORT,
            option_type=OptionType.CALL,
        )
        long_call = _leg(
            _greeks(delta=0.15, gamma=0.02, theta=-0.02, vega=0.10, rho=0.005),
            PositionSide.LONG,
            option_type=OptionType.CALL,
        )
        # Bull put spread (short put higher + long put lower)
        short_put = _leg(
            _greeks(delta=-0.30, gamma=0.03, theta=-0.03, vega=0.15, rho=-0.01),
            PositionSide.SHORT,
            option_type=OptionType.PUT,
        )
        long_put = _leg(
            _greeks(delta=-0.15, gamma=0.02, theta=-0.02, vega=0.10, rho=-0.005),
            PositionSide.LONG,
            option_type=OptionType.PUT,
        )

        result = aggregate_spread_greeks([short_call, long_call, short_put, long_put])
        assert result is not None

        # Delta: -0.30 + 0.15 + 0.30 + (-0.15) = 0.0
        assert result.delta == pytest.approx(0.0, abs=1e-10)
        # Gamma: -0.03 + 0.02 + (-0.03) + 0.02 = -0.02 (short-heavy)
        assert result.gamma == pytest.approx(-0.02, rel=1e-6)
        # Theta: +0.03 + (-0.02) + 0.03 + (-0.02) = 0.02 (positive — collecting premium)
        assert result.theta == pytest.approx(0.02, rel=1e-4)
        # Vega: -0.15 + 0.10 + (-0.15) + 0.10 = -0.10 (short vol)
        assert result.vega == pytest.approx(-0.10, rel=1e-6)

    def test_straddle_greeks(self) -> None:
        """Long ATM call + long ATM put: delta near zero, gamma/vega additive."""
        long_call = _leg(
            _greeks(delta=0.50, gamma=0.05, theta=-0.04, vega=0.25, rho=0.01),
            PositionSide.LONG,
            option_type=OptionType.CALL,
        )
        long_put = _leg(
            _greeks(delta=-0.50, gamma=0.05, theta=-0.04, vega=0.25, rho=-0.01),
            PositionSide.LONG,
            option_type=OptionType.PUT,
        )

        result = aggregate_spread_greeks([long_call, long_put])
        assert result is not None

        # ATM straddle: delta cancels, gamma/vega double
        assert result.delta == pytest.approx(0.0, abs=1e-10)
        assert result.gamma == pytest.approx(0.10, rel=1e-6)  # 0.05 + 0.05
        assert result.theta == pytest.approx(-0.08, rel=1e-4)  # -0.04 + -0.04
        assert result.vega == pytest.approx(0.50, rel=1e-6)  # 0.25 + 0.25
        assert result.rho == pytest.approx(0.0, abs=1e-10)

    def test_short_leg_negates_greeks(self) -> None:
        """Single SHORT leg negates all five Greeks."""
        greeks = _greeks(delta=0.40, gamma=0.03, theta=-0.05, vega=0.18, rho=0.015)
        leg = _leg(greeks, PositionSide.SHORT)

        result = aggregate_spread_greeks([leg])
        assert result is not None

        assert result.delta == pytest.approx(-0.40, rel=1e-6)
        assert result.gamma == pytest.approx(-0.03, rel=1e-6)
        assert result.theta == pytest.approx(0.05, rel=1e-6)
        assert result.vega == pytest.approx(-0.18, rel=1e-6)
        assert result.rho == pytest.approx(-0.015, rel=1e-6)

    def test_quantity_multiplier(self) -> None:
        """leg.quantity=2 doubles the Greek contribution."""
        greeks = _greeks(delta=0.50, gamma=0.04, theta=-0.03, vega=0.20, rho=0.01)
        leg_q1 = _leg(greeks, PositionSide.LONG, quantity=1)
        leg_q2 = _leg(greeks, PositionSide.LONG, quantity=2)

        result_q1 = aggregate_spread_greeks([leg_q1])
        result_q2 = aggregate_spread_greeks([leg_q2])

        assert result_q1 is not None
        assert result_q2 is not None

        # quantity=2 should produce exactly double the Greeks (before clamping)
        # delta 0.50*2 = 1.0, which is at the boundary (not outside), no clamping
        assert result_q2.delta == pytest.approx(result_q1.delta * 2, rel=1e-6)
        assert result_q2.gamma == pytest.approx(result_q1.gamma * 2, rel=1e-6)
        assert result_q2.theta == pytest.approx(result_q1.theta * 2, rel=1e-6)
        assert result_q2.vega == pytest.approx(result_q1.vega * 2, rel=1e-6)
        assert result_q2.rho == pytest.approx(result_q1.rho * 2, rel=1e-6)

    def test_returns_none_for_missing_greeks(self) -> None:
        """Returns None if any leg has contract.greeks=None."""
        good_leg = _leg(
            _greeks(delta=0.50),
            PositionSide.LONG,
        )
        bad_leg = _leg(None, PositionSide.LONG)

        result = aggregate_spread_greeks([good_leg, bad_leg])
        assert result is None

    def test_returns_none_for_empty_legs(self) -> None:
        """Returns None for empty list."""
        result = aggregate_spread_greeks([])
        assert result is None

    def test_second_order_aggregation_all_present(self) -> None:
        """vanna/charm/vomma aggregated when ALL legs have them."""
        leg1 = _leg(
            _greeks(
                delta=0.50,
                gamma=0.04,
                theta=-0.03,
                vega=0.20,
                rho=0.01,
                vanna=0.10,
                charm=-0.02,
                vomma=0.05,
            ),
            PositionSide.LONG,
        )
        leg2 = _leg(
            _greeks(
                delta=0.30,
                gamma=0.03,
                theta=-0.02,
                vega=0.15,
                rho=0.008,
                vanna=0.08,
                charm=-0.01,
                vomma=0.03,
            ),
            PositionSide.SHORT,
        )

        result = aggregate_spread_greeks([leg1, leg2])
        assert result is not None

        # vanna: 0.10 - 0.08 = 0.02
        assert result.vanna == pytest.approx(0.02, rel=1e-6)
        # charm: -0.02 - (-0.01) = -0.01
        assert result.charm == pytest.approx(-0.01, rel=1e-6)
        # vomma: 0.05 - 0.03 = 0.02
        assert result.vomma == pytest.approx(0.02, rel=1e-6)

    def test_second_order_none_when_any_missing(self) -> None:
        """vanna/charm/vomma set to None when any leg is missing them."""
        leg_with = _leg(
            _greeks(
                delta=0.50,
                gamma=0.04,
                theta=-0.03,
                vega=0.20,
                rho=0.01,
                vanna=0.10,
                charm=-0.02,
                vomma=0.05,
            ),
            PositionSide.LONG,
        )
        leg_without = _leg(
            _greeks(delta=0.30, gamma=0.03, theta=-0.02, vega=0.15, rho=0.008),
            PositionSide.SHORT,
        )

        result = aggregate_spread_greeks([leg_with, leg_without])
        assert result is not None

        assert result.vanna is None
        assert result.charm is None
        assert result.vomma is None

    def test_pricing_model_from_first_leg(self) -> None:
        """pricing_model on result matches first leg."""
        bsm_leg = _leg(
            _greeks(delta=0.50, pricing_model=PricingModel.BSM),
            PositionSide.LONG,
        )
        baw_leg = _leg(
            _greeks(delta=0.30, pricing_model=PricingModel.BAW),
            PositionSide.SHORT,
        )

        result = aggregate_spread_greeks([bsm_leg, baw_leg])
        assert result is not None
        assert result.pricing_model == PricingModel.BSM

        # Reverse order — BAW first
        result2 = aggregate_spread_greeks([baw_leg, bsm_leg])
        assert result2 is not None
        assert result2.pricing_model == PricingModel.BAW

    def test_gamma_non_negative_for_long_only(self) -> None:
        """Gamma stays non-negative for long-only positions."""
        long_call = _leg(
            _greeks(delta=0.50, gamma=0.05, theta=-0.04, vega=0.25, rho=0.01),
            PositionSide.LONG,
        )
        long_put = _leg(
            _greeks(delta=-0.50, gamma=0.03, theta=-0.03, vega=0.20, rho=-0.01),
            PositionSide.LONG,
        )

        result = aggregate_spread_greeks([long_call, long_put])
        assert result is not None
        assert result.gamma >= 0.0  # both long → gamma additive
        assert result.gamma == pytest.approx(0.08, rel=1e-6)

    def test_delta_clamped_with_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Aggregate delta outside [-1,1] is clamped with log warning."""
        # Two long calls with delta near 1.0 → aggregate > 1.0
        leg1 = _leg(
            _greeks(delta=0.80, gamma=0.02, theta=-0.02, vega=0.15, rho=0.01),
            PositionSide.LONG,
            quantity=1,
        )
        leg2 = _leg(
            _greeks(delta=0.70, gamma=0.02, theta=-0.02, vega=0.15, rho=0.01),
            PositionSide.LONG,
            quantity=1,
        )

        with caplog.at_level(logging.WARNING, logger="options_arena.pricing.spreads"):
            result = aggregate_spread_greeks([leg1, leg2])

        assert result is not None
        # 0.80 + 0.70 = 1.50 → clamped to 1.0
        assert result.delta == pytest.approx(1.0, abs=1e-10)
        assert "outside [-1, 1]" in caplog.text

    def test_single_leg_returns_same_greeks(self) -> None:
        """Single LONG leg returns identical Greeks."""
        greeks = _greeks(
            delta=0.45,
            gamma=0.035,
            theta=-0.028,
            vega=0.22,
            rho=0.012,
        )
        leg = _leg(greeks, PositionSide.LONG)

        result = aggregate_spread_greeks([leg])
        assert result is not None

        assert result.delta == pytest.approx(greeks.delta, rel=1e-6)
        assert result.gamma == pytest.approx(greeks.gamma, rel=1e-6)
        assert result.theta == pytest.approx(greeks.theta, rel=1e-6)
        assert result.vega == pytest.approx(greeks.vega, rel=1e-6)
        assert result.rho == pytest.approx(greeks.rho, rel=1e-6)
        assert result.pricing_model == greeks.pricing_model

    def test_single_short_leg_negates(self) -> None:
        """Single SHORT leg returns negated Greeks."""
        greeks = _greeks(
            delta=0.45,
            gamma=0.035,
            theta=-0.028,
            vega=0.22,
            rho=0.012,
        )
        leg = _leg(greeks, PositionSide.SHORT)

        result = aggregate_spread_greeks([leg])
        assert result is not None

        assert result.delta == pytest.approx(-0.45, rel=1e-6)
        assert result.gamma == pytest.approx(-0.035, rel=1e-6)
        assert result.theta == pytest.approx(0.028, rel=1e-6)
        assert result.vega == pytest.approx(-0.22, rel=1e-6)
        assert result.rho == pytest.approx(-0.012, rel=1e-6)
