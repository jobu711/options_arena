"""Tests for PositionRecommendation model."""

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models.enums import DeskType, SignalDirection, SpreadType
from options_arena.models.recommendation import PositionRecommendation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_KWARGS: dict[str, object] = {
    "ticker": "AAPL",
    "direction": SignalDirection.BULLISH,
    "confidence": 0.75,
    "recommended_contract": "AAPL 190C 2026-04-18",
    "entry_price": Decimal("3.45"),
    "entry_criteria": "Break above 188 with volume confirmation",
    "exit_criteria": "Close below 185 or 50% profit target",
    "stop_loss": Decimal("1.50"),
    "take_profit": Decimal("6.90"),
    "position_size_pct": 0.05,
    "position_rationale": "Strong trend with moderate IV",
    "risk_reward_ratio": 2.0,
    "max_loss_estimate": "$345 per contract",
    "recommended_strategy": SpreadType.VERTICAL,
    "strategy_rationale": "Bull call spread limits risk in elevated IV environment",
    "summary": "AAPL bullish setup with defined risk",
    "key_factors": ["Strong momentum", "Relative strength"],
    "risk_assessment": "Moderate risk — earnings in 30 days",
    "agent_agreement_score": 0.83,
    "dissenting_desks": [DeskType.CONTRARIAN],
    "model_used": "llama-3.3-70b-versatile",
}


# ---------------------------------------------------------------------------
# Construction & Frozen
# ---------------------------------------------------------------------------


class TestPositionRecommendationConstruction:
    """Tests for valid construction and field access."""

    def test_valid_construction_all_fields(self) -> None:
        rec = PositionRecommendation(**_BASE_KWARGS)
        assert rec.ticker == "AAPL"
        assert rec.direction == SignalDirection.BULLISH
        assert rec.confidence == 0.75
        assert rec.recommended_contract == "AAPL 190C 2026-04-18"
        assert rec.entry_price == Decimal("3.45")
        assert rec.entry_criteria == "Break above 188 with volume confirmation"
        assert rec.exit_criteria == "Close below 185 or 50% profit target"
        assert rec.stop_loss == Decimal("1.50")
        assert rec.take_profit == Decimal("6.90")
        assert rec.position_size_pct == 0.05
        assert rec.risk_reward_ratio == 2.0
        assert rec.max_loss_estimate == "$345 per contract"
        assert rec.recommended_strategy == SpreadType.VERTICAL
        assert rec.summary == "AAPL bullish setup with defined risk"
        assert rec.key_factors == ["Strong momentum", "Relative strength"]
        assert rec.risk_assessment == "Moderate risk — earnings in 30 days"
        assert rec.agent_agreement_score == 0.83
        assert rec.dissenting_desks == [DeskType.CONTRARIAN]
        assert rec.model_used == "llama-3.3-70b-versatile"

    def test_frozen_rejects_mutation(self) -> None:
        rec = PositionRecommendation(**_BASE_KWARGS)
        with pytest.raises(ValidationError):
            rec.confidence = 0.5  # type: ignore[misc]

    def test_optional_decimal_none(self) -> None:
        kw = {**_BASE_KWARGS, "stop_loss": None, "take_profit": None}
        rec = PositionRecommendation(**kw)
        assert rec.stop_loss is None
        assert rec.take_profit is None

    def test_dissenting_desks_defaults_empty(self) -> None:
        kw = {k: v for k, v in _BASE_KWARGS.items() if k != "dissenting_desks"}
        rec = PositionRecommendation(**kw)
        assert rec.dissenting_desks == []

    def test_recommended_strategy_none(self) -> None:
        kw = {**_BASE_KWARGS, "recommended_strategy": None}
        rec = PositionRecommendation(**kw)
        assert rec.recommended_strategy is None

    def test_agent_agreement_score_none(self) -> None:
        kw = {**_BASE_KWARGS, "agent_agreement_score": None}
        rec = PositionRecommendation(**kw)
        assert rec.agent_agreement_score is None


# ---------------------------------------------------------------------------
# Decimal precision round-trip
# ---------------------------------------------------------------------------


class TestDecimalPrecision:
    """Tests for Decimal serialization and round-trip."""

    def test_decimal_precision_json_roundtrip(self) -> None:
        rec = PositionRecommendation(**_BASE_KWARGS)
        json_bytes = rec.model_dump_json()
        restored = PositionRecommendation.model_validate_json(json_bytes)
        assert restored.entry_price == Decimal("3.45")
        assert restored.stop_loss == Decimal("1.50")
        assert restored.take_profit == Decimal("6.90")

    def test_decimal_serialized_as_string(self) -> None:
        rec = PositionRecommendation(**_BASE_KWARGS)
        data = rec.model_dump()
        assert data["entry_price"] == "3.45"
        assert data["stop_loss"] == "1.50"
        assert data["take_profit"] == "6.90"

    def test_optional_decimal_none_serialization(self) -> None:
        kw = {**_BASE_KWARGS, "stop_loss": None, "take_profit": None}
        rec = PositionRecommendation(**kw)
        data = rec.model_dump()
        assert data["stop_loss"] is None
        assert data["take_profit"] is None


# ---------------------------------------------------------------------------
# Confidence validation
# ---------------------------------------------------------------------------


class TestConfidenceValidation:
    """Tests for confidence field validation."""

    def test_confidence_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "confidence": math.nan})

    def test_confidence_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "confidence": math.inf})

    def test_confidence_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "confidence": 1.5})

    def test_confidence_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "confidence": -0.1})

    def test_confidence_accepts_zero(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "confidence": 0.0})
        assert rec.confidence == 0.0

    def test_confidence_accepts_one(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "confidence": 1.0})
        assert rec.confidence == 1.0


# ---------------------------------------------------------------------------
# position_size_pct validation
# ---------------------------------------------------------------------------


class TestPositionSizePctValidation:
    """Tests for position_size_pct bounds [0.0, 1.0]."""

    def test_accepts_zero(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": 0.0})
        assert rec.position_size_pct == 0.0

    def test_accepts_one(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": 1.0})
        assert rec.position_size_pct == 1.0

    def test_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": 1.01})

    def test_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": -0.01})

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": math.nan})

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "position_size_pct": math.inf})


# ---------------------------------------------------------------------------
# risk_reward_ratio validation
# ---------------------------------------------------------------------------


class TestRiskRewardRatioValidation:
    """Tests for risk_reward_ratio (must be finite and > 0)."""

    def test_accepts_positive(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": 3.5})
        assert rec.risk_reward_ratio == 3.5

    def test_rejects_zero(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": 0.0})

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError, match="> 0"):
            PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": -1.0})

    def test_rejects_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": math.inf})

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": math.nan})

    def test_rejects_negative_inf(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "risk_reward_ratio": -math.inf})


# ---------------------------------------------------------------------------
# agent_agreement_score validation
# ---------------------------------------------------------------------------


class TestAgentAgreementScoreValidation:
    """Tests for agent_agreement_score bounds when present vs None."""

    def test_accepts_none(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": None})
        assert rec.agent_agreement_score is None

    def test_accepts_zero(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": 0.0})
        assert rec.agent_agreement_score == 0.0

    def test_accepts_one(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": 1.0})
        assert rec.agent_agreement_score == 1.0

    def test_rejects_above_one(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": 1.5})

    def test_rejects_below_zero(self) -> None:
        with pytest.raises(ValidationError):
            PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": -0.1})

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            PositionRecommendation(**{**_BASE_KWARGS, "agent_agreement_score": math.nan})


# ---------------------------------------------------------------------------
# key_factors validation
# ---------------------------------------------------------------------------


class TestKeyFactorsValidation:
    """Tests for key_factors non-empty list validation."""

    def test_rejects_empty_list(self) -> None:
        with pytest.raises(ValidationError, match="key_factors"):
            PositionRecommendation(**{**_BASE_KWARGS, "key_factors": []})

    def test_accepts_single_item(self) -> None:
        rec = PositionRecommendation(**{**_BASE_KWARGS, "key_factors": ["one"]})
        assert rec.key_factors == ["one"]
