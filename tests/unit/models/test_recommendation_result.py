"""Tests for RecommendationResult model."""

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError
from pydantic_ai.usage import RunUsage

from options_arena.models.enums import DeskType, SignalDirection, SpreadType
from options_arena.models.recommendation import (
    AnyAssessment,
    PositionRecommendation,
    RecommendationResult,
    TrendAssessment,
    VolatilityAssessment,
)
from tests.factories import make_market_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSESSMENT_BASE: dict[str, object] = {
    "direction": SignalDirection.BULLISH,
    "confidence": 0.75,
    "summary": "Uptrend confirmed.",
    "key_factors": ["Strong momentum"],
    "risks": ["Earnings approaching"],
    "contracts_referenced": ["AAPL 190C 2026-04-18"],
    "tools_used": ["fetch_quote"],
    "model_used": "llama-3.3-70b-versatile",
}


def _make_recommendation(**overrides: object) -> PositionRecommendation:
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "recommended_contract": "AAPL 190C 2026-04-18",
        "entry_price": Decimal("3.45"),
        "entry_criteria": "Break above 188",
        "exit_criteria": "Close below 185",
        "position_size_pct": 0.05,
        "position_rationale": "Strong trend",
        "risk_reward_ratio": 2.0,
        "max_loss_estimate": "$345",
        "strategy_rationale": "Bull call spread",
        "summary": "Bullish setup",
        "key_factors": ["Momentum"],
        "risk_assessment": "Moderate",
        "model_used": "llama-3.3-70b-versatile",
    }
    defaults.update(overrides)
    return PositionRecommendation(**defaults)


def _make_assessments() -> list[AnyAssessment]:
    return [
        TrendAssessment(**_ASSESSMENT_BASE, trend_strength=0.85),
        VolatilityAssessment(**_ASSESSMENT_BASE),
    ]


def _make_result(**overrides: object) -> RecommendationResult:
    defaults: dict[str, object] = {
        "context": make_market_context(),
        "assessments": _make_assessments(),
        "recommendation": _make_recommendation(),
        "total_usage": RunUsage(requests=1, input_tokens=100, output_tokens=50),
        "duration_ms": 1500,
        "is_fallback": False,
        "citation_density": 0.42,
    }
    defaults.update(overrides)
    return RecommendationResult(**defaults)


# ---------------------------------------------------------------------------
# Construction & Frozen
# ---------------------------------------------------------------------------


class TestRecommendationResultConstruction:
    """Tests for valid construction and immutability."""

    def test_valid_construction(self) -> None:
        result = _make_result()
        assert result.context.ticker == "AAPL"
        assert len(result.assessments) == 2
        assert result.recommendation.ticker == "AAPL"
        assert result.duration_ms == 1500
        assert result.is_fallback is False
        assert result.citation_density == pytest.approx(0.42)

    def test_frozen_rejects_mutation(self) -> None:
        result = _make_result()
        with pytest.raises(ValidationError):
            result.is_fallback = True  # type: ignore[misc]

    def test_assessments_preserves_subclass_types(self) -> None:
        result = _make_result()
        assert isinstance(result.assessments[0], TrendAssessment)
        assert isinstance(result.assessments[1], VolatilityAssessment)
        assert result.assessments[0].desk == DeskType.TREND
        assert result.assessments[1].desk == DeskType.VOLATILITY

    def test_citation_density_default_zero(self) -> None:
        result = _make_result(citation_density=0.0)
        assert result.citation_density == 0.0


# ---------------------------------------------------------------------------
# Citation density validation
# ---------------------------------------------------------------------------


class TestCitationDensityValidation:
    """Tests for citation_density >= 0 and finite."""

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_result(citation_density=math.nan)

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            _make_result(citation_density=math.inf)

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match=">= 0"):
            _make_result(citation_density=-0.1)

    def test_accepts_zero(self) -> None:
        result = _make_result(citation_density=0.0)
        assert result.citation_density == 0.0

    def test_accepts_above_one(self) -> None:
        # citation_density is not capped at 1.0 — it measures density ratio
        result = _make_result(citation_density=1.5)
        assert result.citation_density == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# JSON round-trip (pieces)
# ---------------------------------------------------------------------------


class TestRecommendationResultSerialization:
    """Test serialization of individual components.

    RecommendationResult may not fully round-trip via model_validate_json due to
    RunUsage (arbitrary type), so we test the components separately.
    """

    def test_recommendation_json_roundtrip(self) -> None:
        rec = _make_recommendation(
            stop_loss=Decimal("1.50"),
            take_profit=Decimal("6.90"),
        )
        json_bytes = rec.model_dump_json()
        restored = PositionRecommendation.model_validate_json(json_bytes)
        assert restored == rec
        assert restored.entry_price == Decimal("3.45")
        assert restored.stop_loss == Decimal("1.50")
        assert restored.take_profit == Decimal("6.90")

    def test_recommendation_preserves_enums(self) -> None:
        rec = _make_recommendation(
            recommended_strategy=SpreadType.VERTICAL,
            dissenting_desks=[DeskType.CONTRARIAN, DeskType.RISK],
        )
        json_bytes = rec.model_dump_json()
        restored = PositionRecommendation.model_validate_json(json_bytes)
        assert restored.recommended_strategy == SpreadType.VERTICAL
        assert restored.dissenting_desks == [DeskType.CONTRARIAN, DeskType.RISK]

    def test_model_dump_includes_all_fields(self) -> None:
        result = _make_result()
        data = result.model_dump()
        assert "context" in data
        assert "assessments" in data
        assert "recommendation" in data
        assert "total_usage" in data
        assert "duration_ms" in data
        assert "is_fallback" in data
        assert "citation_density" in data
