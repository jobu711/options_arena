"""Tests for recommendation response schemas (#670)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from options_arena.api.schemas import (
    AssessmentSummary,
    DebateRequest,
    PositionRecommendationResponse,
    RecommendationResponse,
)


class TestAssessmentSummary:
    """Verify AssessmentSummary schema fields and validation."""

    def test_valid_assessment_summary(self) -> None:
        """Construct with valid fields."""
        summary = AssessmentSummary(
            desk="trend",
            direction="bullish",
            confidence=0.75,
            summary="Strong momentum confirmed by ADX and RSI.",
            key_findings=["ADX > 25", "RSI at 65"],
        )
        assert summary.desk == "trend"
        assert summary.direction == "bullish"
        assert summary.confidence == pytest.approx(0.75)
        assert len(summary.key_findings) == 2

    def test_confidence_must_be_finite(self) -> None:
        """Reject NaN confidence."""
        with pytest.raises(ValueError, match="finite"):
            AssessmentSummary(
                desk="risk",
                direction="neutral",
                confidence=float("nan"),
                summary="test",
                key_findings=["x"],
            )

    def test_confidence_bounds(self) -> None:
        """Reject confidence outside [0, 1]."""
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            AssessmentSummary(
                desk="risk",
                direction="neutral",
                confidence=1.5,
                summary="test",
                key_findings=["x"],
            )

    def test_frozen(self) -> None:
        """AssessmentSummary is frozen."""
        summary = AssessmentSummary(
            desk="flow",
            direction="bearish",
            confidence=0.5,
            summary="test",
            key_findings=["x"],
        )
        with pytest.raises(ValueError):
            summary.desk = "risk"  # type: ignore[misc]


class TestPositionRecommendationResponse:
    """Verify PositionRecommendationResponse schema fields."""

    def test_valid_position_recommendation(self) -> None:
        """Construct with valid fields."""
        rec = PositionRecommendationResponse(
            ticker="AAPL",
            recommended_contract="AAPL 190C 2026-04-18",
            entry_price="5.25",
            stop_loss="3.00",
            take_profit="8.00",
            position_size_pct=0.05,
            risk_reward_ratio=1.5,
            direction="bullish",
            confidence=0.7,
            strategy="vertical",
            strategy_rationale="Bull call spread for defined risk.",
            rationale="Strong momentum with IV expansion likely.",
        )
        assert rec.ticker == "AAPL"
        assert rec.entry_price == "5.25"
        assert rec.confidence == pytest.approx(0.7)
        assert rec.strategy == "vertical"

    def test_optional_fields(self) -> None:
        """Optional fields default to None."""
        rec = PositionRecommendationResponse(
            ticker="MSFT",
            recommended_contract="MSFT 400C",
            entry_price="10.00",
            position_size_pct=0.03,
            risk_reward_ratio=2.0,
            direction="bullish",
            confidence=0.6,
            strategy_rationale="Simple long call.",
            rationale="Breakout confirmed.",
        )
        assert rec.stop_loss is None
        assert rec.take_profit is None
        assert rec.strategy is None
        assert rec.option_type is None
        assert rec.strike is None
        assert rec.expiration is None

    def test_confidence_validation(self) -> None:
        """Reject confidence > 1.0."""
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            PositionRecommendationResponse(
                ticker="AAPL",
                recommended_contract="AAPL 190C",
                entry_price="5.00",
                position_size_pct=0.05,
                risk_reward_ratio=1.5,
                direction="bullish",
                confidence=1.1,
                strategy_rationale="test",
                rationale="test",
            )

    def test_risk_reward_must_be_positive(self) -> None:
        """Reject risk_reward_ratio <= 0."""
        with pytest.raises(ValueError, match="must be > 0"):
            PositionRecommendationResponse(
                ticker="AAPL",
                recommended_contract="AAPL 190C",
                entry_price="5.00",
                position_size_pct=0.05,
                risk_reward_ratio=0.0,
                direction="bullish",
                confidence=0.5,
                strategy_rationale="test",
                rationale="test",
            )

    def test_position_size_bounds(self) -> None:
        """Reject position_size_pct outside [0, 1]."""
        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            PositionRecommendationResponse(
                ticker="AAPL",
                recommended_contract="AAPL 190C",
                entry_price="5.00",
                position_size_pct=1.5,
                risk_reward_ratio=1.0,
                direction="bullish",
                confidence=0.5,
                strategy_rationale="test",
                rationale="test",
            )


class TestRecommendationResponse:
    """Verify RecommendationResponse schema."""

    def _make_response(self, **kw: object) -> RecommendationResponse:
        """Helper to build a valid RecommendationResponse."""
        defaults: dict[str, object] = {
            "id": 1,
            "ticker": "AAPL",
            "assessments": [
                AssessmentSummary(
                    desk="trend",
                    direction="bullish",
                    confidence=0.8,
                    summary="Strong uptrend.",
                    key_findings=["ADX > 25"],
                ),
            ],
            "recommendation": PositionRecommendationResponse(
                ticker="AAPL",
                recommended_contract="AAPL 190C 2026-04-18",
                entry_price="5.25",
                position_size_pct=0.05,
                risk_reward_ratio=1.5,
                direction="bullish",
                confidence=0.7,
                strategy_rationale="Bull call spread.",
                rationale="Strong momentum.",
            ),
            "is_fallback": False,
            "recommendation_protocol": "unified_v1",
            "duration_ms": 3000,
            "total_tokens": 5000,
            "citation_density": 0.45,
            "model_used": "llama-3.3-70b-versatile",
            "created_at": datetime(2026, 3, 22, 12, 0, 0, tzinfo=UTC),
        }
        defaults.update(kw)
        return RecommendationResponse(**defaults)

    def test_serialization(self) -> None:
        """RecommendationResponse serializes to JSON and back."""
        resp = self._make_response()
        data = resp.model_dump()
        assert "assessments" in data
        assert "recommendation" in data
        assert data["ticker"] == "AAPL"
        assert data["is_fallback"] is False
        assert data["recommendation_protocol"] == "unified_v1"

    def test_json_roundtrip(self) -> None:
        """RecommendationResponse survives JSON roundtrip."""
        resp = self._make_response()
        json_str = resp.model_dump_json()
        restored = RecommendationResponse.model_validate_json(json_str)
        assert restored.id == resp.id
        assert restored.ticker == resp.ticker
        assert len(restored.assessments) == len(resp.assessments)
        assert restored.recommendation.ticker == resp.recommendation.ticker

    def test_citation_density_validation(self) -> None:
        """Reject negative citation_density."""
        with pytest.raises(ValueError, match="citation_density must be >= 0"):
            self._make_response(citation_density=-0.1)

    def test_citation_density_nan(self) -> None:
        """Reject NaN citation_density."""
        with pytest.raises(ValueError, match="citation_density must be finite"):
            self._make_response(citation_density=float("nan"))

    def test_created_at_must_be_utc(self) -> None:
        """Reject non-UTC created_at."""
        with pytest.raises(ValueError, match="must be UTC"):
            self._make_response(created_at=datetime(2026, 1, 1, 0, 0, 0))

    def test_fallback_response(self) -> None:
        """Verify is_fallback flag serializes correctly."""
        resp = self._make_response(is_fallback=True)
        assert resp.is_fallback is True
        data = resp.model_dump()
        assert data["is_fallback"] is True

    def test_scan_run_id_optional(self) -> None:
        """scan_run_id defaults to None."""
        resp = self._make_response()
        assert resp.scan_run_id is None


class TestDebateRequestNoDead:
    """Verify DebateRequest no longer has dead fields."""

    def test_no_enable_rebuttal(self) -> None:
        """enable_rebuttal is not a field."""
        req = DebateRequest(ticker="AAPL")
        assert not hasattr(req, "enable_rebuttal")

    def test_no_enable_volatility_agent(self) -> None:
        """enable_volatility_agent is not a field."""
        req = DebateRequest(ticker="AAPL")
        assert not hasattr(req, "enable_volatility_agent")

    def test_basic_construction(self) -> None:
        """DebateRequest still works with ticker only."""
        req = DebateRequest(ticker="aapl")
        assert req.ticker == "AAPL"
        assert req.scan_id is None
