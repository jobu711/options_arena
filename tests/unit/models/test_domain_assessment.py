"""Tests for DomainAssessment hierarchy and AnyAssessment discriminated union."""

import math

import pytest
from pydantic import TypeAdapter, ValidationError

from options_arena.models.enums import (
    DeskType,
    IVTermStructureShape,
    SignalDirection,
    ValuationSignal,
    VolRegime,
)
from options_arena.models.recommendation import (
    AnyAssessment,
    ContrarianAssessment,
    DomainAssessment,
    FlowAssessment,
    FundamentalAssessment,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_KWARGS: dict[str, object] = {
    "direction": SignalDirection.BULLISH,
    "confidence": 0.75,
    "summary": "Uptrend confirmed by multiple indicators.",
    "key_factors": ["Strong momentum"],
    "risks": ["Earnings approaching"],
    "contracts_referenced": ["AAPL 240C 2026-04-18"],
    "tools_used": ["fetch_quote", "compute_indicators"],
    "model_used": "llama-3.3-70b-versatile",
}


# ---------------------------------------------------------------------------
# DomainAssessment base tests
# ---------------------------------------------------------------------------


class TestDomainAssessment:
    """Tests for the DomainAssessment base model."""

    def test_valid_construction(self) -> None:
        a = DomainAssessment(desk=DeskType.TREND, **_BASE_KWARGS)
        assert a.desk == DeskType.TREND
        assert a.direction == SignalDirection.BULLISH
        assert a.confidence == 0.75
        assert a.key_factors == ["Strong momentum"]
        assert a.model_used == "llama-3.3-70b-versatile"

    def test_frozen_rejects_mutation(self) -> None:
        a = DomainAssessment(desk=DeskType.TREND, **_BASE_KWARGS)
        with pytest.raises(ValidationError):
            a.confidence = 0.5  # type: ignore[misc]

    def test_confidence_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            DomainAssessment(
                desk=DeskType.TREND,
                **{**_BASE_KWARGS, "confidence": math.nan},
            )

    def test_confidence_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            DomainAssessment(
                desk=DeskType.TREND,
                **{**_BASE_KWARGS, "confidence": math.inf},
            )

    def test_confidence_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            DomainAssessment(
                desk=DeskType.TREND,
                **{**_BASE_KWARGS, "confidence": 1.5},
            )

    def test_confidence_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            DomainAssessment(
                desk=DeskType.TREND,
                **{**_BASE_KWARGS, "confidence": -0.1},
            )

    def test_key_factors_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError, match="key_factors"):
            DomainAssessment(
                desk=DeskType.TREND,
                **{**_BASE_KWARGS, "key_factors": []},
            )


# ---------------------------------------------------------------------------
# TrendAssessment
# ---------------------------------------------------------------------------


class TestTrendAssessment:
    """Tests for the TrendAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = TrendAssessment(
            **_BASE_KWARGS,
            trend_strength=0.85,
            momentum_signal="strong bullish crossover",
        )
        assert a.desk == DeskType.TREND
        assert a.trend_strength == 0.85
        assert a.momentum_signal == "strong bullish crossover"

    def test_desk_literal_enforced(self) -> None:
        with pytest.raises(ValidationError):
            TrendAssessment(desk=DeskType.RISK, **_BASE_KWARGS)  # type: ignore[arg-type]

    def test_trend_strength_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            TrendAssessment(**_BASE_KWARGS, trend_strength=math.nan)

    def test_trend_strength_accepts_none(self) -> None:
        a = TrendAssessment(**_BASE_KWARGS)
        assert a.trend_strength is None


# ---------------------------------------------------------------------------
# VolatilityAssessment
# ---------------------------------------------------------------------------


class TestVolatilityAssessment:
    """Tests for VolatilityAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = VolatilityAssessment(
            **_BASE_KWARGS,
            iv_regime=VolRegime.ELEVATED,
            vol_skew_assessment="steep put skew",
            term_structure_shape=IVTermStructureShape.BACKWARDATION,
        )
        assert a.desk == DeskType.VOLATILITY
        assert a.iv_regime == VolRegime.ELEVATED
        assert a.term_structure_shape == IVTermStructureShape.BACKWARDATION


# ---------------------------------------------------------------------------
# FlowAssessment
# ---------------------------------------------------------------------------


class TestFlowAssessment:
    """Tests for FlowAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = FlowAssessment(
            **_BASE_KWARGS,
            flow_bias="bullish call sweep",
            unusual_activity_noted=True,
        )
        assert a.desk == DeskType.FLOW
        assert a.flow_bias == "bullish call sweep"
        assert a.unusual_activity_noted is True

    def test_unusual_activity_defaults_false(self) -> None:
        a = FlowAssessment(**_BASE_KWARGS)
        assert a.unusual_activity_noted is False


# ---------------------------------------------------------------------------
# FundamentalAssessment
# ---------------------------------------------------------------------------


class TestFundamentalAssessment:
    """Tests for FundamentalAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = FundamentalAssessment(
            **_BASE_KWARGS,
            valuation_signal=ValuationSignal.UNDERVALUED,
            catalyst_timeline="Q2 earnings in 14 days",
        )
        assert a.desk == DeskType.FUNDAMENTAL
        assert a.valuation_signal == ValuationSignal.UNDERVALUED
        assert a.catalyst_timeline == "Q2 earnings in 14 days"


# ---------------------------------------------------------------------------
# RiskDeskAssessment
# ---------------------------------------------------------------------------


class TestRiskDeskAssessment:
    """Tests for RiskDeskAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = RiskDeskAssessment(
            **_BASE_KWARGS,
            max_position_pct=0.05,
            hedging_suggestion="Buy protective put",
            portfolio_correlation_note="High correlation with QQQ",
        )
        assert a.desk == DeskType.RISK
        assert a.max_position_pct == 0.05
        assert a.hedging_suggestion == "Buy protective put"

    def test_max_position_pct_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=1.5)

    def test_max_position_pct_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=-0.01)

    def test_max_position_pct_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=math.nan)

    def test_max_position_pct_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=math.inf)

    def test_max_position_pct_accepts_none(self) -> None:
        a = RiskDeskAssessment(**_BASE_KWARGS)
        assert a.max_position_pct is None

    def test_max_position_pct_accepts_boundary_zero(self) -> None:
        a = RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=0.0)
        assert a.max_position_pct == 0.0

    def test_max_position_pct_accepts_boundary_one(self) -> None:
        a = RiskDeskAssessment(**_BASE_KWARGS, max_position_pct=1.0)
        assert a.max_position_pct == 1.0


# ---------------------------------------------------------------------------
# ContrarianAssessment
# ---------------------------------------------------------------------------


class TestContrarianAssessment:
    """Tests for ContrarianAssessment subclass."""

    def test_construct_with_domain_fields(self) -> None:
        a = ContrarianAssessment(
            **_BASE_KWARGS,
            consensus_challenged="Consensus is bullish",
            contrarian_thesis="Market is overextended; reversion likely",
        )
        assert a.desk == DeskType.CONTRARIAN
        assert a.consensus_challenged == "Consensus is bullish"
        assert a.contrarian_thesis == "Market is overextended; reversion likely"


# ---------------------------------------------------------------------------
# AnyAssessment discriminated union
# ---------------------------------------------------------------------------


class TestAnyAssessmentUnion:
    """Tests for AnyAssessment discriminated union polymorphic round-trip."""

    @staticmethod
    def _build_all_subclasses() -> list[
        TrendAssessment
        | VolatilityAssessment
        | FlowAssessment
        | FundamentalAssessment
        | RiskDeskAssessment
        | ContrarianAssessment
    ]:
        return [
            TrendAssessment(
                **_BASE_KWARGS,
                trend_strength=0.9,
                momentum_signal="golden cross",
            ),
            VolatilityAssessment(
                **_BASE_KWARGS,
                iv_regime=VolRegime.LOW,
                term_structure_shape=IVTermStructureShape.CONTANGO,
            ),
            FlowAssessment(
                **_BASE_KWARGS,
                flow_bias="neutral",
                unusual_activity_noted=False,
            ),
            FundamentalAssessment(
                **_BASE_KWARGS,
                valuation_signal=ValuationSignal.FAIRLY_VALUED,
            ),
            RiskDeskAssessment(
                **_BASE_KWARGS,
                max_position_pct=0.02,
                hedging_suggestion="collar",
            ),
            ContrarianAssessment(
                **_BASE_KWARGS,
                contrarian_thesis="Bearish divergence forming",
            ),
        ]

    def test_round_trip_preserves_types(self) -> None:
        items = self._build_all_subclasses()
        adapter = TypeAdapter(list[AnyAssessment])
        raw = adapter.dump_json(items)
        restored = adapter.validate_json(raw)

        assert len(restored) == 6
        assert isinstance(restored[0], TrendAssessment)
        assert isinstance(restored[1], VolatilityAssessment)
        assert isinstance(restored[2], FlowAssessment)
        assert isinstance(restored[3], FundamentalAssessment)
        assert isinstance(restored[4], RiskDeskAssessment)
        assert isinstance(restored[5], ContrarianAssessment)

    def test_round_trip_preserves_domain_fields(self) -> None:
        items = self._build_all_subclasses()
        adapter = TypeAdapter(list[AnyAssessment])
        raw = adapter.dump_json(items)
        restored = adapter.validate_json(raw)

        trend = restored[0]
        assert isinstance(trend, TrendAssessment)
        assert trend.trend_strength == 0.9
        assert trend.momentum_signal == "golden cross"

        risk = restored[4]
        assert isinstance(risk, RiskDeskAssessment)
        assert risk.max_position_pct == 0.02
        assert risk.hedging_suggestion == "collar"

    @pytest.mark.parametrize(
        ("subclass", "desk"),
        [
            (TrendAssessment, DeskType.TREND),
            (VolatilityAssessment, DeskType.VOLATILITY),
            (FlowAssessment, DeskType.FLOW),
            (FundamentalAssessment, DeskType.FUNDAMENTAL),
            (RiskDeskAssessment, DeskType.RISK),
            (ContrarianAssessment, DeskType.CONTRARIAN),
        ],
    )
    def test_each_subclass_deserializes_via_union(
        self,
        subclass: type[DomainAssessment],
        desk: DeskType,
    ) -> None:
        item = subclass(desk=desk, **_BASE_KWARGS)
        adapter = TypeAdapter(AnyAssessment)
        raw = adapter.dump_json(item)
        restored = adapter.validate_json(raw)
        assert isinstance(restored, subclass)
        assert restored.desk == desk

    def test_unknown_desk_value_rejected(self) -> None:
        adapter = TypeAdapter(AnyAssessment)
        # Forge JSON with an invalid desk value
        bad_json = (
            b'{"desk":"research","direction":"bullish","confidence":0.5,'
            b'"summary":"x","key_factors":["y"],"risks":[],'
            b'"contracts_referenced":[],"tools_used":[],"model_used":"m"}'
        )
        with pytest.raises(ValidationError):
            adapter.validate_json(bad_json)
