"""Tests for direction-aware vol-mispricing tiebreaker in select_by_delta().

Verifies that when two contracts have identical effective delta distance,
the tiebreaker prefers direction-favorable vol mispricing:
  - BULLISH: prefers lower residual (underpriced vol = cheaper to buy)
  - BEARISH: prefers higher residual (overpriced vol = richer to sell)
  - NEUTRAL / None: no tiebreaker effect
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from options_arena.models.enums import (
    ExerciseStyle,
    OptionType,
    PricingModel,
    SignalDirection,
)
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import select_by_delta


def _make_greeks(delta: float = 0.35) -> OptionGreeks:
    """Create test Greeks with the specified delta."""
    return OptionGreeks(
        delta=delta,
        gamma=0.05,
        theta=-0.03,
        vega=0.15,
        rho=0.01,
        pricing_model=PricingModel.BAW,
    )


def _make_contract(
    strike: str,
    delta: float = 0.35,
    bid: str = "5.00",
    ask: str = "5.50",
    open_interest: int = 1000,
) -> OptionContract:
    """Create a test call contract with specific strike and delta."""
    exp = datetime.now(UTC).date() + timedelta(days=45)
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal(strike),
        expiration=exp,
        bid=Decimal(bid),
        ask=Decimal(ask),
        last=Decimal("5.25"),
        volume=100,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.30,
        greeks=_make_greeks(delta),
    )


class TestDeltaTiebreaker:
    """Tests for direction-aware vol-mispricing tiebreaker."""

    def test_bullish_prefers_underpriced(self) -> None:
        """BULLISH: contract with lower residual (underpriced) preferred."""
        c_overpriced = _make_contract("150.00", delta=0.35)
        c_underpriced = _make_contract("155.00", delta=0.35)

        residuals: dict[tuple[Decimal, datetime.date], float] = {
            (c_overpriced.strike, c_overpriced.expiration): 1.5,  # overpriced
            (c_underpriced.strike, c_underpriced.expiration): -1.5,  # underpriced
        }

        result = select_by_delta(
            [c_overpriced, c_underpriced],
            delta_target=0.35,
            direction=SignalDirection.BULLISH,
            surface_residuals=residuals,
        )

        assert result is not None
        assert result.strike == Decimal("155.00")

    def test_bearish_prefers_overpriced(self) -> None:
        """BEARISH: contract with higher residual (overpriced) preferred."""
        c_overpriced = _make_contract("150.00", delta=0.35)
        c_underpriced = _make_contract("155.00", delta=0.35)

        residuals: dict[tuple[Decimal, datetime.date], float] = {
            (c_overpriced.strike, c_overpriced.expiration): 1.5,  # overpriced
            (c_underpriced.strike, c_underpriced.expiration): -1.5,  # underpriced
        }

        result = select_by_delta(
            [c_overpriced, c_underpriced],
            delta_target=0.35,
            direction=SignalDirection.BEARISH,
            surface_residuals=residuals,
        )

        assert result is not None
        assert result.strike == Decimal("150.00")

    def test_no_residuals_no_effect(self) -> None:
        """No surface_residuals means no tiebreaker — falls back to strike order."""
        c1 = _make_contract("150.00", delta=0.35)
        c2 = _make_contract("155.00", delta=0.35)

        result = select_by_delta(
            [c1, c2],
            delta_target=0.35,
            direction=SignalDirection.BULLISH,
            surface_residuals=None,
        )

        # Without tiebreaker, both have same effective distance;
        # tie broken by strike (lower first)
        assert result is not None
        assert result.strike == Decimal("150.00")

    def test_no_direction_no_effect(self) -> None:
        """direction=None means no tiebreaker — falls back to strike order."""
        c1 = _make_contract("150.00", delta=0.35)
        c2 = _make_contract("155.00", delta=0.35)

        residuals: dict[tuple[Decimal, datetime.date], float] = {
            (c1.strike, c1.expiration): 2.0,
            (c2.strike, c2.expiration): -2.0,
        }

        result = select_by_delta(
            [c1, c2],
            delta_target=0.35,
            direction=None,
            surface_residuals=residuals,
        )

        # No direction = no tiebreaker, sort by strike
        assert result is not None
        assert result.strike == Decimal("150.00")

    def test_neutral_no_tiebreaker(self) -> None:
        """NEUTRAL direction produces no tiebreaker effect."""
        c1 = _make_contract("150.00", delta=0.35)
        c2 = _make_contract("155.00", delta=0.35)

        residuals: dict[tuple[Decimal, datetime.date], float] = {
            (c1.strike, c1.expiration): 2.0,
            (c2.strike, c2.expiration): -2.0,
        }

        result = select_by_delta(
            [c1, c2],
            delta_target=0.35,
            direction=SignalDirection.NEUTRAL,
            surface_residuals=residuals,
        )

        # NEUTRAL = no tiebreaker, sort by strike
        assert result is not None
        assert result.strike == Decimal("150.00")

    def test_missing_residual_for_contract(self) -> None:
        """Contract not in surface_residuals map gets tb=0.0."""
        c1 = _make_contract("150.00", delta=0.35)
        c2 = _make_contract("155.00", delta=0.35)

        # Only c2 has a residual
        residuals: dict[tuple[Decimal, datetime.date], float] = {
            (c2.strike, c2.expiration): -2.0,  # underpriced
        }

        result = select_by_delta(
            [c1, c2],
            delta_target=0.35,
            direction=SignalDirection.BULLISH,
            surface_residuals=residuals,
        )

        # c1 tb=0.0, c2 tb=-2.0 (bullish: lower is better)
        # c2 wins tiebreaker
        assert result is not None
        assert result.strike == Decimal("155.00")

    def test_backward_compatible_no_new_params(self) -> None:
        """select_by_delta works without new params (backward compat)."""
        c = _make_contract("150.00", delta=0.35)

        result = select_by_delta([c], delta_target=0.35)

        assert result is not None
        assert result.strike == Decimal("150.00")
