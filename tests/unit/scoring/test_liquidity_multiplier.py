"""Tests for _compute_liquidity_score and liquidity-adjusted select_by_delta."""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from options_arena.models.config import PricingConfig
from options_arena.models.enums import ExerciseStyle, GreeksSource, OptionType, PricingModel
from options_arena.models.options import OptionContract, OptionGreeks
from options_arena.scoring.contracts import _compute_liquidity_score, select_by_delta


def _make_contract(
    *,
    strike: float = 100.0,
    bid: float = 9.5,
    ask: float = 10.5,
    open_interest: int = 1000,
    delta: float = 0.35,
) -> OptionContract:
    """Build a contract with Greeks for testing."""
    return OptionContract(
        ticker="TEST",
        option_type=OptionType.CALL,
        strike=Decimal(str(strike)),
        expiration=date.today() + timedelta(days=30),
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        volume=100,
        open_interest=open_interest,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.25,
        greeks=OptionGreeks(
            delta=delta,
            gamma=0.03,
            theta=-0.05,
            vega=0.15,
            rho=0.01,
            pricing_model=PricingModel.BAW,
            source=GreeksSource.COMPUTED,
        ),
    )


class TestComputeLiquidityScore:
    def test_perfect_liquidity(self) -> None:
        """Tight spread + high OI -> score near 1.0."""
        c = _make_contract(bid=99.99, ask=100.01, open_interest=10000)
        score = _compute_liquidity_score(c, max_spread_pct=0.10)
        assert score > 0.9

    def test_poor_liquidity(self) -> None:
        """Wide spread + low OI -> score near 0.0."""
        c = _make_contract(bid=90.0, ask=110.0, open_interest=1)
        score = _compute_liquidity_score(c, max_spread_pct=0.10)
        assert score < 0.15

    def test_zero_mid(self) -> None:
        """Zero mid -> spread component is 0.0."""
        c = _make_contract(bid=0.0, ask=0.0, open_interest=1000)
        score = _compute_liquidity_score(c, max_spread_pct=0.10)
        # Only OI contributes: log10(1001)/4 * 0.3 ~ 0.225
        assert score == pytest.approx(min(math.log10(1001) / 4.0, 1.0) * 0.3, abs=0.01)

    def test_zero_oi(self) -> None:
        """Zero OI -> OI component is 0.0."""
        c = _make_contract(bid=99.0, ask=101.0, open_interest=0)
        score = _compute_liquidity_score(c, max_spread_pct=0.30)
        # Only spread contributes: (1 - 0.02/0.30) * 0.7 ~ 0.653
        expected_spread = max(1.0 - (2.0 / 100.0) / 0.30, 0.0) * 0.7
        assert score == pytest.approx(expected_spread, abs=0.01)

    def test_spread_weight_dominates(self) -> None:
        """Spread weight (0.7) > OI weight (0.3)."""
        # Perfect spread, zero OI
        c1 = _make_contract(bid=100.0, ask=100.0, open_interest=0)
        # Zero spread component (wide spread), perfect OI
        c2 = _make_contract(bid=50.0, ask=150.0, open_interest=10000)
        s1 = _compute_liquidity_score(c1, max_spread_pct=0.10)
        s2 = _compute_liquidity_score(c2, max_spread_pct=0.10)
        assert s1 > s2  # spread-dominant wins


class TestSelectByDeltaLiquidity:
    def test_equal_delta_prefers_liquid(self) -> None:
        """Equally-delta-distant contracts: liquid one wins."""
        liquid = _make_contract(bid=99.0, ask=101.0, open_interest=5000, delta=0.36)
        illiquid = _make_contract(bid=90.0, ask=110.0, open_interest=100, delta=0.34, strike=105.0)
        # Both have delta distance of 0.01 from target 0.35
        cfg = PricingConfig(max_spread_pct=0.30)
        result = select_by_delta([liquid, illiquid], config=cfg)
        assert result is not None
        assert result.strike == liquid.strike

    def test_closer_delta_beats_better_liquidity(self) -> None:
        """Closer delta wins even with worse liquidity."""
        close_delta = _make_contract(bid=90.0, ask=110.0, open_interest=100, delta=0.34)
        far_delta = _make_contract(
            bid=99.0, ask=101.0, open_interest=5000, delta=0.25, strike=105.0
        )
        cfg = PricingConfig(max_spread_pct=0.30)
        result = select_by_delta([close_delta, far_delta], config=cfg)
        assert result is not None
        assert result.strike == close_delta.strike

    def test_backward_compat_no_liquidity_change(self) -> None:
        """Single-candidate selection unchanged."""
        c = _make_contract(delta=0.35)
        result = select_by_delta([c])
        assert result is not None
        assert result.strike == c.strike

    def test_extreme_spread_clamps_to_zero(self) -> None:
        """Spread > max_spread_pct -> component clamped at 0.0."""
        c = _make_contract(bid=50.0, ask=150.0, open_interest=0)
        score = _compute_liquidity_score(c, max_spread_pct=0.10)
        assert score == pytest.approx(0.0, abs=0.01)
