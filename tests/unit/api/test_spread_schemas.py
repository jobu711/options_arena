"""Tests for spread-related API schemas (#521).

Tests cover:
  - SpreadLegDetail and SpreadDetail construction
  - DebateResultDetail with and without spread
  - JSON roundtrip for SpreadDetail
  - spread_detail_from_analysis helper conversion
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from options_arena.api.schemas import (
    DebateResultDetail,
    SpreadDetail,
    SpreadLegDetail,
    TickerDetail,
    spread_detail_from_analysis,
)
from options_arena.models import SignalDirection
from tests.factories import make_spread_analysis


def _make_spread_leg_detail(**kw: object) -> SpreadLegDetail:
    """Create a SpreadLegDetail with sensible defaults."""
    defaults: dict[str, object] = {
        "option_type": "call",
        "strike": "150.00",
        "expiration": "2026-05-15",
        "side": "long",
        "quantity": 1,
        "bid": "5.00",
        "ask": "5.50",
        "delta": 0.45,
    }
    defaults.update(kw)
    return SpreadLegDetail(**defaults)


def _make_spread_detail(**kw: object) -> SpreadDetail:
    """Create a SpreadDetail with sensible defaults."""
    defaults: dict[str, object] = {
        "spread_type": "vertical",
        "legs": [_make_spread_leg_detail()],
        "net_premium": "2.50",
        "max_profit": "2.50",
        "max_loss": "2.50",
        "risk_reward_ratio": 1.0,
        "pop_estimate": 0.55,
        "breakevens": ["152.50"],
        "strategy_rationale": "Bull call spread to limit risk.",
    }
    defaults.update(kw)
    return SpreadDetail(**defaults)


class TestSpreadLegDetail:
    """Tests for SpreadLegDetail schema."""

    def test_construction(self) -> None:
        """SpreadLegDetail constructs with all fields."""
        leg = _make_spread_leg_detail()
        assert leg.option_type == "call"
        assert leg.strike == "150.00"
        assert leg.side == "long"
        assert leg.quantity == 1
        assert leg.delta == pytest.approx(0.45)

    def test_optional_fields_none(self) -> None:
        """SpreadLegDetail accepts None for optional fields."""
        leg = _make_spread_leg_detail(bid=None, ask=None, delta=None)
        assert leg.bid is None
        assert leg.ask is None
        assert leg.delta is None

    def test_nan_delta_rejected(self) -> None:
        """SpreadLegDetail rejects NaN delta."""
        with pytest.raises(Exception, match="finite"):
            _make_spread_leg_detail(delta=float("nan"))


class TestSpreadDetail:
    """Tests for SpreadDetail schema."""

    def test_construction(self) -> None:
        """SpreadDetail constructs with all fields."""
        detail = _make_spread_detail()
        assert detail.spread_type == "vertical"
        assert len(detail.legs) == 1
        assert detail.net_premium == "2.50"
        assert detail.max_profit == "2.50"
        assert detail.max_loss == "2.50"
        assert detail.risk_reward_ratio == pytest.approx(1.0)
        assert detail.pop_estimate == pytest.approx(0.55)
        assert detail.breakevens == ["152.50"]
        assert detail.strategy_rationale == "Bull call spread to limit risk."

    def test_optional_risk_metrics_none(self) -> None:
        """SpreadDetail accepts None for risk_reward_ratio and pop_estimate."""
        detail = _make_spread_detail(risk_reward_ratio=None, pop_estimate=None)
        assert detail.risk_reward_ratio is None
        assert detail.pop_estimate is None

    def test_nan_risk_reward_rejected(self) -> None:
        """SpreadDetail rejects NaN risk_reward_ratio."""
        with pytest.raises(Exception, match="finite"):
            _make_spread_detail(risk_reward_ratio=float("nan"))

    def test_nan_pop_estimate_rejected(self) -> None:
        """SpreadDetail rejects NaN pop_estimate."""
        with pytest.raises(Exception, match="finite"):
            _make_spread_detail(pop_estimate=float("nan"))

    def test_json_roundtrip(self) -> None:
        """SpreadDetail survives JSON serialization/deserialization."""
        original = _make_spread_detail()
        json_str = original.model_dump_json()
        restored = SpreadDetail.model_validate_json(json_str)
        assert restored.spread_type == original.spread_type
        assert restored.net_premium == original.net_premium
        assert restored.max_profit == original.max_profit
        assert len(restored.legs) == len(original.legs)
        assert restored.risk_reward_ratio == pytest.approx(original.risk_reward_ratio)  # type: ignore[arg-type]

    def test_multiple_legs(self) -> None:
        """SpreadDetail handles 4-leg iron condor."""
        legs = [
            _make_spread_leg_detail(strike="140.00", side="long", option_type="put"),
            _make_spread_leg_detail(strike="145.00", side="short", option_type="put"),
            _make_spread_leg_detail(strike="155.00", side="short", option_type="call"),
            _make_spread_leg_detail(strike="160.00", side="long", option_type="call"),
        ]
        detail = _make_spread_detail(
            spread_type="iron_condor",
            legs=legs,
        )
        assert len(detail.legs) == 4
        assert detail.spread_type == "iron_condor"


class TestDebateResultWithSpread:
    """Tests for DebateResultDetail with spread field."""

    def test_with_spread(self) -> None:
        """DebateResultDetail includes spread when present."""
        spread = _make_spread_detail()
        detail = DebateResultDetail(
            id=1,
            ticker="AAPL",
            is_fallback=False,
            model_name="test",
            duration_ms=1000,
            total_tokens=500,
            created_at=datetime.now(UTC),
            spread=spread,
        )
        assert detail.spread is not None
        assert detail.spread.spread_type == "vertical"

    def test_without_spread(self) -> None:
        """DebateResultDetail works when spread is None."""
        detail = DebateResultDetail(
            id=1,
            ticker="AAPL",
            is_fallback=False,
            model_name="test",
            duration_ms=1000,
            total_tokens=500,
            created_at=datetime.now(UTC),
        )
        assert detail.spread is None


class TestTickerDetailWithSpread:
    """Tests for TickerDetail with spread field."""

    def test_with_spread(self) -> None:
        """TickerDetail includes spread when present."""
        spread = _make_spread_detail()
        detail = TickerDetail(
            ticker="AAPL",
            composite_score=78.5,
            direction=SignalDirection.BULLISH,
            contracts=[],
            spread=spread,
        )
        assert detail.spread is not None

    def test_without_spread(self) -> None:
        """TickerDetail works when spread is None (backward compatible)."""
        detail = TickerDetail(
            ticker="AAPL",
            composite_score=78.5,
            direction=SignalDirection.BULLISH,
            contracts=[],
        )
        assert detail.spread is None


class TestSpreadDetailFromAnalysis:
    """Tests for spread_detail_from_analysis helper."""

    def test_basic_conversion(self) -> None:
        """Converts SpreadAnalysis to SpreadDetail with correct fields."""
        analysis = make_spread_analysis()
        detail = spread_detail_from_analysis(analysis)

        assert detail.spread_type == "vertical"
        assert len(detail.legs) == 2
        assert detail.net_premium == "2.50"
        assert detail.max_profit == "2.50"
        assert detail.max_loss == "2.50"
        assert detail.risk_reward_ratio == pytest.approx(1.0)
        assert detail.pop_estimate == pytest.approx(0.55)
        assert detail.breakevens == ["152.50"]

    def test_leg_fields_mapped(self) -> None:
        """Leg fields are correctly mapped from SpreadAnalysis."""
        analysis = make_spread_analysis()
        detail = spread_detail_from_analysis(analysis)

        first_leg = detail.legs[0]
        assert first_leg.option_type == "call"
        assert first_leg.side == "long"
        assert first_leg.quantity == 1
        # Factory creates contracts without greeks, so delta should be None
        assert first_leg.delta is None

    def test_unlimited_max_profit(self) -> None:
        """Sentinel Decimal('999999.99') converts to 'Unlimited'."""
        analysis = make_spread_analysis(max_profit=Decimal("999999.99"))
        detail = spread_detail_from_analysis(analysis)
        assert detail.max_profit == "Unlimited"

    def test_nan_risk_reward_becomes_none(self) -> None:
        """NaN risk_reward_ratio becomes None in SpreadDetail."""
        analysis = make_spread_analysis(risk_reward_ratio=float("nan"))
        detail = spread_detail_from_analysis(analysis)
        assert detail.risk_reward_ratio is None
