"""Tests for agent fields on DebateResult.

Tests cover:
  - Agent fields default to None when not provided (backward-compatible)
  - Agent fields can be populated with typed agent outputs
  - JSON roundtrip preserves agent fields
  - Frozen immutability preserved with agent fields
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.models import (
    AgentResponse,
    CatalystImpact,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    RiskLevel,
    SignalDirection,
    TradeThesis,
)

# ---------------------------------------------------------------------------
# Agent field defaults
# ---------------------------------------------------------------------------


class TestV2FieldDefaults:
    """DebateResult agent fields default to None for backward compat."""

    def test_agent_fields_default_to_none(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """Constructing DebateResult without agent fields gives None defaults."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1000,
            is_fallback=False,
        )
        assert result.flow_response is None
        assert result.fundamental_response is None
        assert result.risk_response is None
        assert result.contrarian_response is None


# ---------------------------------------------------------------------------
# Agent fields populated
# ---------------------------------------------------------------------------


class TestV2FieldsPopulated:
    """DebateResult agent fields can be populated with typed agent outputs."""

    @pytest.fixture()
    def mock_flow_thesis(self) -> FlowThesis:
        """Realistic FlowThesis for test assertions."""
        return FlowThesis(
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            gex_interpretation="Positive GEX suggests dealer hedging supports upside.",
            smart_money_signal="Large call sweeps detected at 190 strike.",
            oi_analysis="OI concentrated at 185-195 range, bullish skew.",
            volume_confirmation="Volume 2x average, confirming directional move.",
            key_flow_factors=["GEX positive", "Call sweeps at 190"],
            model_used="llama-3.3-70b-versatile",
        )

    @pytest.fixture()
    def mock_fundamental_thesis(self) -> FundamentalThesis:
        """Realistic FundamentalThesis for test assertions."""
        return FundamentalThesis(
            direction=SignalDirection.BULLISH,
            confidence=0.65,
            catalyst_impact=CatalystImpact.HIGH,
            earnings_assessment="Strong Q4 earnings with revenue beat.",
            iv_crush_risk="Moderate — IV at 45th percentile, limited crush expected.",
            key_fundamental_factors=["Revenue beat", "Guidance raised"],
            model_used="llama-3.3-70b-versatile",
        )

    @pytest.fixture()
    def mock_risk_assessment(self) -> RiskAssessment:
        """Realistic RiskAssessment for test assertions."""
        return RiskAssessment(
            risk_level=RiskLevel.MODERATE,
            confidence=0.72,
            pop_estimate=0.55,
            max_loss_estimate="$480 per contract (premium paid).",
            key_risks=["Earnings next week", "Elevated theta decay"],
            risk_mitigants=["Positive GEX support", "Strong sector momentum"],
            model_used="llama-3.3-70b-versatile",
        )

    @pytest.fixture()
    def mock_contrarian_thesis(self) -> ContrarianThesis:
        """Realistic ContrarianThesis for test assertions."""
        return ContrarianThesis(
            dissent_direction=SignalDirection.BEARISH,
            dissent_confidence=0.4,
            primary_challenge="RSI divergence suggests momentum fading.",
            overlooked_risks=["Supply chain disruption", "Sector rotation risk"],
            consensus_weakness="Bull case relies heavily on single earnings beat.",
            alternative_scenario="Reversion to 180 support if earnings disappoint.",
            model_used="llama-3.3-70b-versatile",
        )

    def test_agent_fields_populated(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
        mock_flow_thesis: FlowThesis,
        mock_fundamental_thesis: FundamentalThesis,
        mock_risk_assessment: RiskAssessment,
        mock_contrarian_thesis: ContrarianThesis,
    ) -> None:
        """DebateResult can be constructed with all 4 agent outputs."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=2500,
            is_fallback=False,
            flow_response=mock_flow_thesis,
            fundamental_response=mock_fundamental_thesis,
            risk_response=mock_risk_assessment,
            contrarian_response=mock_contrarian_thesis,
        )
        assert result.flow_response is not None
        assert isinstance(result.flow_response, FlowThesis)
        assert result.flow_response.direction == SignalDirection.BULLISH

        assert result.fundamental_response is not None
        assert isinstance(result.fundamental_response, FundamentalThesis)
        assert result.fundamental_response.catalyst_impact == CatalystImpact.HIGH

        assert result.risk_response is not None
        assert isinstance(result.risk_response, RiskAssessment)
        assert result.risk_response.risk_level == RiskLevel.MODERATE

        assert result.contrarian_response is not None
        assert isinstance(result.contrarian_response, ContrarianThesis)
        assert result.contrarian_response.dissent_direction == SignalDirection.BEARISH

    def test_json_roundtrip_with_agent_fields(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
        mock_flow_thesis: FlowThesis,
        mock_fundamental_thesis: FundamentalThesis,
        mock_risk_assessment: RiskAssessment,
        mock_contrarian_thesis: ContrarianThesis,
    ) -> None:
        """JSON roundtrip preserves agent fields."""
        original = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=2500,
            is_fallback=False,
            flow_response=mock_flow_thesis,
            fundamental_response=mock_fundamental_thesis,
            risk_response=mock_risk_assessment,
            contrarian_response=mock_contrarian_thesis,
        )
        json_str = original.model_dump_json()
        restored = DebateResult.model_validate_json(json_str)

        assert restored.flow_response is not None
        assert restored.flow_response.direction == SignalDirection.BULLISH
        assert restored.flow_response.confidence == pytest.approx(0.7)

        assert restored.fundamental_response is not None
        assert restored.fundamental_response.catalyst_impact == CatalystImpact.HIGH

        assert restored.risk_response is not None
        assert restored.risk_response.risk_level == RiskLevel.MODERATE
        assert restored.risk_response.pop_estimate == pytest.approx(0.55)

        assert restored.contrarian_response is not None
        assert restored.contrarian_response.dissent_direction == SignalDirection.BEARISH
        assert restored.contrarian_response.dissent_confidence == pytest.approx(0.4)

    def test_json_roundtrip_with_fields_none(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """JSON roundtrip preserves None agent fields."""
        original = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1000,
            is_fallback=False,
        )
        json_str = original.model_dump_json()
        restored = DebateResult.model_validate_json(json_str)

        assert restored.flow_response is None
        assert restored.fundamental_response is None
        assert restored.risk_response is None
        assert restored.contrarian_response is None


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------


class TestV2FrozenImmutability:
    """DebateResult with agent fields remains frozen (immutable)."""

    def test_frozen_immutability_preserved(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """DebateResult rejects attribute mutation."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1000,
            is_fallback=False,
        )
        with pytest.raises(ValidationError):
            result.flow_response = None  # type: ignore[misc]

    def test_model_dump_includes_agent_fields(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """model_dump() includes all agent fields."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1000,
            is_fallback=False,
        )
        dump = result.model_dump()
        assert "flow_response" in dump
        assert "fundamental_response" in dump
        assert "risk_response" in dump
        assert "contrarian_response" in dump
