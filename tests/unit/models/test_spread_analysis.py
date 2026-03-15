"""Tests for SpreadAnalysis model, SpreadConfig, and related factories.

Covers construction, frozen immutability, JSON roundtrip with Decimal precision,
validator edge cases (pop_estimate, breakevens, risk_reward_ratio), and SpreadConfig
defaults plus environment variable overrides.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models.config import AppSettings, SpreadConfig
from options_arena.models.enums import (
    PositionSide,
    PricingModel,
    SpreadType,
    VolRegime,
)
from options_arena.models.options import (
    OptionGreeks,
    SpreadAnalysis,
)
from tests.factories import make_spread_analysis, make_spread_leg

# ---------------------------------------------------------------------------
# SpreadAnalysis — construction
# ---------------------------------------------------------------------------


class TestSpreadAnalysisConstruction:
    """Test SpreadAnalysis model construction with valid data."""

    def test_construction_with_valid_data(self) -> None:
        """Happy-path: construct SpreadAnalysis with all fields populated."""
        analysis = make_spread_analysis()

        assert analysis.spread.spread_type == SpreadType.VERTICAL
        assert analysis.net_premium == Decimal("2.50")
        assert analysis.max_profit == Decimal("2.50")
        assert analysis.max_loss == Decimal("2.50")
        assert analysis.breakevens == [Decimal("152.50")]
        assert analysis.risk_reward_ratio == pytest.approx(1.0)
        assert analysis.pop_estimate == pytest.approx(0.55)
        assert analysis.net_greeks is None
        assert analysis.strategy_rationale == ""
        assert analysis.iv_regime is None

    def test_construction_with_all_optional_fields(self) -> None:
        """Construct with net_greeks, strategy_rationale, and iv_regime set."""
        greeks = OptionGreeks(
            delta=0.25,
            gamma=0.02,
            theta=-0.05,
            vega=0.10,
            rho=0.01,
            pricing_model=PricingModel.BAW,
        )
        analysis = make_spread_analysis(
            net_greeks=greeks,
            strategy_rationale="Bullish vertical spread targeting earnings move.",
            iv_regime=VolRegime.ELEVATED,
        )

        assert analysis.net_greeks is not None
        assert analysis.net_greeks.delta == pytest.approx(0.25)
        assert analysis.strategy_rationale == "Bullish vertical spread targeting earnings move."
        assert analysis.iv_regime == VolRegime.ELEVATED

    def test_construction_with_multiple_breakevens(self) -> None:
        """Iron condors and butterflies can have multiple breakevens."""
        analysis = make_spread_analysis(
            breakevens=[Decimal("148.00"), Decimal("157.00")],
        )
        assert len(analysis.breakevens) == 2
        assert analysis.breakevens[0] == Decimal("148.00")
        assert analysis.breakevens[1] == Decimal("157.00")


# ---------------------------------------------------------------------------
# SpreadAnalysis — frozen immutability
# ---------------------------------------------------------------------------


class TestSpreadAnalysisFrozen:
    """Test that SpreadAnalysis is frozen (immutable after construction)."""

    def test_frozen_rejects_mutation(self) -> None:
        """Attempting to set a field on a frozen model raises ValidationError."""
        analysis = make_spread_analysis()

        with pytest.raises(ValidationError):
            analysis.net_premium = Decimal("999.99")  # type: ignore[misc]

    def test_frozen_rejects_pop_mutation(self) -> None:
        """Attempting to mutate pop_estimate raises ValidationError."""
        analysis = make_spread_analysis()

        with pytest.raises(ValidationError):
            analysis.pop_estimate = 0.99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SpreadAnalysis — JSON roundtrip
# ---------------------------------------------------------------------------


class TestSpreadAnalysisRoundtrip:
    """Test JSON roundtrip preserves Decimal precision."""

    def test_json_roundtrip_decimal_precision(self) -> None:
        """Decimal fields survive JSON serialization without float precision loss."""
        analysis = make_spread_analysis(
            net_premium=Decimal("1.05"),
            max_profit=Decimal("3.95"),
            max_loss=Decimal("1.05"),
            breakevens=[Decimal("151.05")],
        )

        json_str = analysis.model_dump_json()
        restored = SpreadAnalysis.model_validate_json(json_str)

        # Decimal precision preserved through string serialization
        assert restored.net_premium == Decimal("1.05")
        assert restored.max_profit == Decimal("3.95")
        assert restored.max_loss == Decimal("1.05")
        assert restored.breakevens == [Decimal("151.05")]

    def test_json_roundtrip_with_all_fields(self) -> None:
        """Full roundtrip with net_greeks and iv_regime populated."""
        greeks = OptionGreeks(
            delta=0.30,
            gamma=0.01,
            theta=-0.03,
            vega=0.08,
            rho=0.005,
            pricing_model=PricingModel.BSM,
        )
        analysis = make_spread_analysis(
            net_greeks=greeks,
            strategy_rationale="Test rationale.",
            iv_regime=VolRegime.LOW,
        )

        json_str = analysis.model_dump_json()
        restored = SpreadAnalysis.model_validate_json(json_str)

        assert restored.net_greeks is not None
        assert restored.net_greeks.delta == pytest.approx(0.30)
        assert restored.iv_regime == VolRegime.LOW
        assert restored.strategy_rationale == "Test rationale."

    def test_model_dump_preserves_nan_risk_reward(self) -> None:
        """NaN risk_reward_ratio is preserved in model_dump() (Python dict).

        Pydantic serializes NaN to null in JSON, so true JSON roundtrip is
        not possible for NaN floats. The Python dict roundtrip works fine.
        """
        analysis = make_spread_analysis(risk_reward_ratio=float("nan"))

        dumped = analysis.model_dump()
        assert math.isnan(dumped["risk_reward_ratio"])


# ---------------------------------------------------------------------------
# SpreadAnalysis — validator: pop_estimate
# ---------------------------------------------------------------------------


class TestSpreadAnalysisPopEstimate:
    """Test pop_estimate validation edge cases."""

    def test_pop_estimate_rejects_out_of_range_high(self) -> None:
        """pop_estimate > 1.0 is rejected."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            make_spread_analysis(pop_estimate=1.01)

    def test_pop_estimate_rejects_out_of_range_low(self) -> None:
        """pop_estimate < 0.0 is rejected."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            make_spread_analysis(pop_estimate=-0.01)

    def test_pop_estimate_rejects_nan(self) -> None:
        """NaN pop_estimate is rejected (isfinite check)."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            make_spread_analysis(pop_estimate=float("nan"))

    def test_pop_estimate_rejects_inf(self) -> None:
        """Infinity pop_estimate is rejected (isfinite check)."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            make_spread_analysis(pop_estimate=float("inf"))

    def test_pop_estimate_accepts_boundaries(self) -> None:
        """pop_estimate of 0.0 and 1.0 are valid boundary values."""
        low = make_spread_analysis(pop_estimate=0.0)
        high = make_spread_analysis(pop_estimate=1.0)

        assert low.pop_estimate == pytest.approx(0.0)
        assert high.pop_estimate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# SpreadAnalysis — validator: breakevens
# ---------------------------------------------------------------------------


class TestSpreadAnalysisBreakevens:
    """Test breakevens validation."""

    def test_breakevens_rejects_empty(self) -> None:
        """Empty breakevens list is rejected."""
        with pytest.raises(ValidationError, match="breakevens"):
            make_spread_analysis(breakevens=[])


# ---------------------------------------------------------------------------
# SpreadAnalysis — risk_reward_ratio
# ---------------------------------------------------------------------------


class TestSpreadAnalysisRiskReward:
    """Test risk_reward_ratio allows NaN (for undefined ratios)."""

    def test_risk_reward_allows_nan(self) -> None:
        """NaN is valid for risk_reward_ratio (undefined when max_loss is zero)."""
        analysis = make_spread_analysis(risk_reward_ratio=float("nan"))
        assert math.isnan(analysis.risk_reward_ratio)

    def test_risk_reward_allows_positive_inf(self) -> None:
        """Positive infinity is valid for risk_reward_ratio (credit spreads)."""
        analysis = make_spread_analysis(risk_reward_ratio=float("inf"))
        assert math.isinf(analysis.risk_reward_ratio)

    def test_risk_reward_allows_normal_values(self) -> None:
        """Normal float values are valid for risk_reward_ratio."""
        analysis = make_spread_analysis(risk_reward_ratio=2.5)
        assert analysis.risk_reward_ratio == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# SpreadLeg factory
# ---------------------------------------------------------------------------


class TestSpreadLegFactory:
    """Test the make_spread_leg factory."""

    def test_default_construction(self) -> None:
        """Factory produces a valid SpreadLeg with defaults."""
        leg = make_spread_leg()

        assert leg.side == PositionSide.LONG
        assert leg.quantity == 1
        assert leg.contract.ticker == "AAPL"

    def test_override_side(self) -> None:
        """Factory respects side override."""
        leg = make_spread_leg(side=PositionSide.SHORT)
        assert leg.side == PositionSide.SHORT


# ---------------------------------------------------------------------------
# SpreadConfig
# ---------------------------------------------------------------------------


class TestSpreadConfig:
    """Test SpreadConfig model."""

    def test_default_construction(self) -> None:
        """SpreadConfig() produces valid defaults."""
        config = SpreadConfig()

        assert config.vertical_width == 5
        assert config.iron_condor_wing_width == 5
        assert config.short_leg_delta == pytest.approx(0.30)
        assert config.min_pop == pytest.approx(0.40)
        assert config.max_legs == 4
        assert config.enabled is True

    def test_custom_values(self) -> None:
        """SpreadConfig accepts custom values within bounds."""
        config = SpreadConfig(
            vertical_width=10,
            iron_condor_wing_width=3,
            short_leg_delta=0.20,
            min_pop=0.50,
            max_legs=6,
            enabled=False,
        )

        assert config.vertical_width == 10
        assert config.iron_condor_wing_width == 3
        assert config.short_leg_delta == pytest.approx(0.20)
        assert config.min_pop == pytest.approx(0.50)
        assert config.max_legs == 6
        assert config.enabled is False

    def test_rejects_nan_short_leg_delta(self) -> None:
        """NaN short_leg_delta is rejected."""
        with pytest.raises(ValidationError, match="short_leg_delta"):
            SpreadConfig(short_leg_delta=float("nan"))

    def test_rejects_invalid_min_pop(self) -> None:
        """min_pop outside [0.0, 1.0] is rejected."""
        with pytest.raises(ValidationError, match="min_pop"):
            SpreadConfig(min_pop=1.5)

    def test_rejects_zero_width(self) -> None:
        """Zero vertical_width is rejected."""
        with pytest.raises(ValidationError, match="width"):
            SpreadConfig(vertical_width=0)

    def test_rejects_max_legs_below_2(self) -> None:
        """max_legs below 2 is rejected."""
        with pytest.raises(ValidationError, match="max_legs"):
            SpreadConfig(max_legs=1)

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """SpreadConfig fields are overridden via ARENA_SPREAD__ env vars."""
        monkeypatch.setenv("ARENA_SPREAD__VERTICAL_WIDTH", "10")
        monkeypatch.setenv("ARENA_SPREAD__ENABLED", "false")

        settings = AppSettings()

        assert settings.spread.vertical_width == 10
        assert settings.spread.enabled is False

    def test_nested_in_appsettings(self) -> None:
        """SpreadConfig appears as a field on AppSettings with correct defaults."""
        settings = AppSettings()

        assert hasattr(settings, "spread")
        assert isinstance(settings.spread, SpreadConfig)
        assert settings.spread.vertical_width == 5
        assert settings.spread.enabled is True
