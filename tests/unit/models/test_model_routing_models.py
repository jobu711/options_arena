"""Tests for model routing models: ModelTier, DeskMetrics, AssessmentSummary, RecommendationCost, RoutingConfig."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AssessmentSummary,
    DeskMetrics,
    DeskType,
    ModelTier,
    RecommendationCost,
    RecommendationResult,
    RoutingConfig,
    SignalDirection,
)
from options_arena.models.analysis import MarketContext


# ---------------------------------------------------------------------------
# ModelTier
# ---------------------------------------------------------------------------


class TestModelTier:
    def test_member_count(self) -> None:
        assert len(ModelTier) == 3

    def test_values(self) -> None:
        assert ModelTier.FAST == "fast"
        assert ModelTier.STANDARD == "standard"
        assert ModelTier.PREMIUM == "premium"

    def test_is_strenum(self) -> None:
        assert issubclass(ModelTier, StrEnum)

    def test_json_roundtrip(self) -> None:
        for tier in ModelTier:
            assert ModelTier(tier.value) == tier


# ---------------------------------------------------------------------------
# DeskMetrics
# ---------------------------------------------------------------------------


class TestDeskMetrics:
    def test_construction(self) -> None:
        m = DeskMetrics(
            desk=DeskType.TREND,
            status="success",
            duration_ms=1500,
            model_tier=ModelTier.STANDARD,
            model_used="llama-3.3-70b-versatile",
            input_tokens=1000,
            output_tokens=500,
        )
        assert m.desk == DeskType.TREND
        assert m.status == "success"
        assert m.duration_ms == 1500
        assert m.model_tier == ModelTier.STANDARD
        assert m.input_tokens == 1000
        assert m.output_tokens == 500

    def test_frozen(self) -> None:
        m = DeskMetrics(
            desk=DeskType.RISK,
            status="success",
            duration_ms=100,
            model_tier=ModelTier.STANDARD,
            model_used="test",
        )
        with pytest.raises(ValidationError):
            m.status = "fallback"  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        m = DeskMetrics(
            desk=DeskType.VOLATILITY,
            status="fallback",
            duration_ms=0,
            model_tier=ModelTier.FAST,
            model_used="llama-3.1-8b-instant",
            input_tokens=0,
            output_tokens=0,
        )
        assert DeskMetrics.model_validate_json(m.model_dump_json()) == m

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duration_ms"):
            DeskMetrics(
                desk=DeskType.TREND,
                status="success",
                duration_ms=-1,
                model_tier=ModelTier.STANDARD,
                model_used="test",
            )

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValidationError, match="token count"):
            DeskMetrics(
                desk=DeskType.TREND,
                status="success",
                duration_ms=100,
                model_tier=ModelTier.STANDARD,
                model_used="test",
                input_tokens=-1,
            )

    def test_default_zero_tokens(self) -> None:
        m = DeskMetrics(
            desk=DeskType.FLOW,
            status="fallback",
            duration_ms=50,
            model_tier=ModelTier.FAST,
            model_used="test",
        )
        assert m.input_tokens == 0
        assert m.output_tokens == 0


# ---------------------------------------------------------------------------
# AssessmentSummary
# ---------------------------------------------------------------------------


class TestAssessmentSummary:
    def test_construction(self) -> None:
        s = AssessmentSummary(
            direction_votes={SignalDirection.BULLISH: 4, SignalDirection.BEARISH: 2},
            avg_confidence=0.72,
            disagreement_desks=[DeskType.RISK, DeskType.CONTRARIAN],
            risk_flags=["earnings proximity", "high IV"],
            data_completeness=0.85,
        )
        assert s.avg_confidence == 0.72
        assert len(s.disagreement_desks) == 2
        assert s.data_completeness == 0.85

    def test_frozen(self) -> None:
        s = AssessmentSummary(
            direction_votes={SignalDirection.BULLISH: 6},
            avg_confidence=0.5,
            disagreement_desks=[],
            risk_flags=[],
            data_completeness=0.9,
        )
        with pytest.raises(ValidationError):
            s.avg_confidence = 0.8  # type: ignore[misc]

    def test_json_roundtrip(self) -> None:
        s = AssessmentSummary(
            direction_votes={
                SignalDirection.BULLISH: 3,
                SignalDirection.BEARISH: 2,
                SignalDirection.NEUTRAL: 1,
            },
            avg_confidence=0.65,
            disagreement_desks=[DeskType.CONTRARIAN],
            risk_flags=["low liquidity"],
            data_completeness=0.7,
        )
        assert AssessmentSummary.model_validate_json(s.model_dump_json()) == s

    def test_nan_avg_confidence_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            AssessmentSummary(
                direction_votes={SignalDirection.BULLISH: 6},
                avg_confidence=float("nan"),
                disagreement_desks=[],
                risk_flags=[],
                data_completeness=0.5,
            )

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="avg_confidence"):
            AssessmentSummary(
                direction_votes={SignalDirection.BULLISH: 6},
                avg_confidence=1.5,
                disagreement_desks=[],
                risk_flags=[],
                data_completeness=0.5,
            )

    def test_completeness_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="data_completeness"):
            AssessmentSummary(
                direction_votes={SignalDirection.BULLISH: 6},
                avg_confidence=0.5,
                disagreement_desks=[],
                risk_flags=[],
                data_completeness=-0.1,
            )

    def test_nan_completeness_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            AssessmentSummary(
                direction_votes={SignalDirection.BULLISH: 6},
                avg_confidence=0.5,
                disagreement_desks=[],
                risk_flags=[],
                data_completeness=float("nan"),
            )


# ---------------------------------------------------------------------------
# RecommendationCost
# ---------------------------------------------------------------------------


class TestRecommendationCost:
    def test_construction(self) -> None:
        c = RecommendationCost(
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cost_usd=0.0042,
            tier_distribution={ModelTier.FAST: 2, ModelTier.STANDARD: 3, ModelTier.PREMIUM: 1},
        )
        assert c.total_input_tokens == 5000
        assert c.total_output_tokens == 2000
        assert c.total_cost_usd == pytest.approx(0.0042)
        assert c.tier_distribution[ModelTier.FAST] == 2

    def test_frozen(self) -> None:
        c = RecommendationCost(
            total_input_tokens=100,
            total_output_tokens=50,
            total_cost_usd=0.01,
            tier_distribution={ModelTier.STANDARD: 6},
        )
        with pytest.raises(ValidationError):
            c.total_cost_usd = 0.02  # type: ignore[misc]

    def test_nan_cost_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            RecommendationCost(
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost_usd=float("nan"),
                tier_distribution={},
            )

    def test_inf_cost_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            RecommendationCost(
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost_usd=float("inf"),
                tier_distribution={},
            )

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValidationError, match="token count"):
            RecommendationCost(
                total_input_tokens=-1,
                total_output_tokens=50,
                total_cost_usd=0.01,
                tier_distribution={},
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError, match="total_cost_usd"):
            RecommendationCost(
                total_input_tokens=100,
                total_output_tokens=50,
                total_cost_usd=-0.01,
                tier_distribution={},
            )

    def test_json_roundtrip(self) -> None:
        c = RecommendationCost(
            total_input_tokens=5000,
            total_output_tokens=2000,
            total_cost_usd=0.005,
            tier_distribution={ModelTier.FAST: 1, ModelTier.PREMIUM: 1},
        )
        assert RecommendationCost.model_validate_json(c.model_dump_json()) == c

    def test_empty_tier_distribution(self) -> None:
        c = RecommendationCost(
            total_input_tokens=0,
            total_output_tokens=0,
            total_cost_usd=0.0,
            tier_distribution={},
        )
        assert c.tier_distribution == {}


# ---------------------------------------------------------------------------
# RoutingConfig
# ---------------------------------------------------------------------------


class TestRoutingConfig:
    def test_defaults(self) -> None:
        rc = RoutingConfig()
        assert rc.enable_model_routing is False
        assert rc.complexity_threshold_fast == pytest.approx(0.3)
        assert rc.complexity_threshold_premium == pytest.approx(0.7)
        assert rc.fast_model == "llama-3.1-8b-instant"
        assert rc.premium_model == ""

    def test_threshold_validation_equal_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <"):
            RoutingConfig(
                complexity_threshold_fast=0.5,
                complexity_threshold_premium=0.5,
            )

    def test_threshold_validation_inverted_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must be <"):
            RoutingConfig(
                complexity_threshold_fast=0.8,
                complexity_threshold_premium=0.3,
            )

    def test_nan_threshold_rejected(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            RoutingConfig(
                complexity_threshold_fast=float("nan"),
            )

    def test_threshold_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError, match="threshold"):
            RoutingConfig(
                complexity_threshold_fast=-0.1,
                complexity_threshold_premium=0.7,
            )

    def test_nested_on_debate_config(self) -> None:
        from options_arena.models.config import DebateConfig

        dc = DebateConfig()
        assert isinstance(dc.routing, RoutingConfig)
        assert dc.routing.enable_model_routing is False

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from options_arena.models.config import AppSettings

        monkeypatch.setenv("ARENA_DEBATE__ROUTING__ENABLE_MODEL_ROUTING", "true")
        settings = AppSettings()
        assert settings.debate.routing.enable_model_routing is True

    def test_custom_cost_map(self) -> None:
        rc = RoutingConfig(
            cost_per_million_tokens={"custom-model": 1.5, "cheap-model": 0.01},
        )
        assert rc.cost_per_million_tokens["custom-model"] == pytest.approx(1.5)

    def test_cost_map_has_defaults(self) -> None:
        rc = RoutingConfig()
        assert "llama-3.3-70b-versatile" in rc.cost_per_million_tokens
        assert "llama-3.1-8b-instant" in rc.cost_per_million_tokens


# ---------------------------------------------------------------------------
# RecommendationResult extensions
# ---------------------------------------------------------------------------


class TestRecommendationResultExtended:
    @pytest.fixture()
    def _minimal_result_kwargs(self) -> dict:  # type: ignore[type-arg]
        from datetime import UTC, datetime

        from pydantic_ai.usage import RunUsage

        from options_arena.models.enums import ExerciseStyle, MacdSignal, SpreadType
        from options_arena.models.recommendation import (
            PositionRecommendation,
            TrendAssessment,
        )

        context = MarketContext(
            ticker="AAPL",
            current_price=Decimal("190.00"),
            price_52w_high=Decimal("200.00"),
            price_52w_low=Decimal("150.00"),
            rsi_14=55.0,
            macd_signal=MacdSignal.BULLISH_CROSSOVER,
            next_earnings=None,
            dte_target=45,
            target_strike=Decimal("195.00"),
            target_delta=0.35,
            sector="Technology",
            dividend_yield=0.005,
            exercise_style=ExerciseStyle.AMERICAN,
            data_timestamp=datetime.now(UTC),
        )
        assessment = TrendAssessment(
            desk=DeskType.TREND,
            direction=SignalDirection.BULLISH,
            confidence=0.75,
            summary="Strong uptrend",
            key_factors=["RSI above 50"],
            risks=["Earnings risk"],
            contracts_referenced=["AAPL 195C"],
            tools_used=["fetch_quote"],
            model_used="test-model",
        )
        rec = PositionRecommendation(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.8,
            recommended_contract="AAPL 195C 2026-05-16",
            entry_price=Decimal("5.50"),
            entry_criteria="Break above 192",
            exit_criteria="Close below 185",
            stop_loss=Decimal("3.00"),
            take_profit=Decimal("8.50"),
            position_size_pct=0.05,
            position_rationale="Moderate conviction",
            risk_reward_ratio=1.75,
            max_loss_estimate="$300",
            recommended_strategy=SpreadType.VERTICAL,
            strategy_rationale="Simple directional bet",
            summary="Buy AAPL calls",
            key_factors=["Strong trend"],
            risk_assessment="Moderate risk",
            model_used="test-model",
        )
        return {
            "context": context,
            "assessments": [assessment],
            "recommendation": rec,
            "total_usage": RunUsage(),
            "duration_ms": 5000,
            "is_fallback": False,
        }

    def test_desk_metrics_default_empty(
        self, _minimal_result_kwargs: dict,  # type: ignore[type-arg]
    ) -> None:
        result = RecommendationResult(**_minimal_result_kwargs)
        assert result.desk_metrics == []

    def test_cost_default_none(
        self, _minimal_result_kwargs: dict,  # type: ignore[type-arg]
    ) -> None:
        result = RecommendationResult(**_minimal_result_kwargs)
        assert result.cost is None

    def test_assessment_summary_default_none(
        self, _minimal_result_kwargs: dict,  # type: ignore[type-arg]
    ) -> None:
        result = RecommendationResult(**_minimal_result_kwargs)
        assert result.assessment_summary is None

    def test_with_metrics_and_cost(
        self, _minimal_result_kwargs: dict,  # type: ignore[type-arg]
    ) -> None:
        metrics = [
            DeskMetrics(
                desk=DeskType.TREND,
                status="success",
                duration_ms=1200,
                model_tier=ModelTier.FAST,
                model_used="llama-3.1-8b-instant",
                input_tokens=500,
                output_tokens=200,
            ),
        ]
        summary = AssessmentSummary(
            direction_votes={SignalDirection.BULLISH: 5, SignalDirection.BEARISH: 1},
            avg_confidence=0.72,
            disagreement_desks=[DeskType.CONTRARIAN],
            risk_flags=["earnings in 5 days"],
            data_completeness=0.85,
        )
        cost = RecommendationCost(
            total_input_tokens=3000,
            total_output_tokens=1500,
            total_cost_usd=0.003,
            tier_distribution={ModelTier.FAST: 1},
        )
        result = RecommendationResult(
            **_minimal_result_kwargs,
            desk_metrics=metrics,
            assessment_summary=summary,
            cost=cost,
        )
        assert len(result.desk_metrics) == 1
        assert result.desk_metrics[0].desk == DeskType.TREND
        assert result.assessment_summary is not None
        assert result.assessment_summary.avg_confidence == pytest.approx(0.72)
        assert result.cost is not None
        assert result.cost.total_cost_usd == pytest.approx(0.003)
