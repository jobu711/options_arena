"""Tests for shared prompt appendix, output validator helpers, and prompt integration.

Tests cover:
  - PROMPT_RULES_APPENDIX is present in all three agent system prompts
  - RISK_STRATEGY_TREE is present in risk prompt only (not bull/bear)
  - build_cleaned_agent_response() strips <think> tags from all text fields
  - build_cleaned_trade_thesis() strips <think> tags from all text fields
  - build_cleaned_agent_response() returns original when no tags (identity)
  - build_cleaned_trade_thesis() returns original when no tags (identity)
  - Version headers are v2.0 on all three agent prompts
"""

from __future__ import annotations

import inspect

import pytest
from pydantic_ai import models

import options_arena.agents.bear as bear_module
import options_arena.agents.bull as bull_module
import options_arena.agents.risk as risk_module
from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX,
    build_cleaned_agent_response,
    build_cleaned_trade_thesis,
    build_cleaned_volatility_thesis,
)
from options_arena.agents.bear import BEAR_SYSTEM_PROMPT
from options_arena.agents.bull import BULL_SYSTEM_PROMPT
from options_arena.agents.risk import RISK_STRATEGY_TREE, RISK_SYSTEM_PROMPT
from options_arena.models import (
    AgentResponse,
    SignalDirection,
    SpreadType,
    TradeThesis,
    VolatilityThesis,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# --- Fixtures ---


@pytest.fixture()
def agent_response_with_think_tags() -> AgentResponse:
    """AgentResponse with <think> tags in text fields."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="<think>Let me reason about this.</think>RSI at 62.3 is bullish.",
        key_points=[
            "<think>Analyzing momentum</think>RSI trending up",
            "Volume increasing",
        ],
        risks_cited=["<think>risks</think>Earnings next week"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


@pytest.fixture()
def agent_response_clean() -> AgentResponse:
    """AgentResponse with no <think> tags."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up", "Volume increasing"],
        risks_cited=["Earnings next week"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


@pytest.fixture()
def trade_thesis_with_think_tags() -> TradeThesis:
    """TradeThesis with <think> tags in text fields."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="<think>Weighing both cases.</think>Moderate bullish case.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=[
            "<think>factor analysis</think>RSI trending up",
            "Sector strength",
        ],
        risk_assessment="<think>sizing</think>Moderate risk. Position: 2%.",
        recommended_strategy=None,
    )


@pytest.fixture()
def trade_thesis_clean() -> TradeThesis:
    """TradeThesis with no <think> tags."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case supported by momentum indicators.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up", "Sector strength"],
        risk_assessment="Moderate risk. Position sizing: 2% of portfolio.",
        recommended_strategy=None,
    )


# --- Prompt integration tests ---


class TestPromptAppendixIntegration:
    """Verify PROMPT_RULES_APPENDIX is appended to all agent prompts."""

    def test_bull_prompt_contains_appendix(self) -> None:
        assert "Confidence calibration" in BULL_SYSTEM_PROMPT
        assert "Data citation rules" in BULL_SYSTEM_PROMPT
        assert "Data anchors" in BULL_SYSTEM_PROMPT

    def test_bear_prompt_contains_appendix(self) -> None:
        assert "Confidence calibration" in BEAR_SYSTEM_PROMPT
        assert "Data citation rules" in BEAR_SYSTEM_PROMPT
        assert "Data anchors" in BEAR_SYSTEM_PROMPT

    def test_risk_prompt_contains_appendix(self) -> None:
        assert "Confidence calibration" in RISK_SYSTEM_PROMPT
        assert "Data citation rules" in RISK_SYSTEM_PROMPT
        assert "Data anchors" in RISK_SYSTEM_PROMPT

    def test_risk_prompt_contains_strategy_tree(self) -> None:
        assert "Strategy selection decision tree" in RISK_SYSTEM_PROMPT
        assert "iron_condor" in RISK_SYSTEM_PROMPT
        assert "straddle" in RISK_SYSTEM_PROMPT
        assert "vertical" in RISK_SYSTEM_PROMPT
        assert "calendar" in RISK_SYSTEM_PROMPT
        assert "strangle" in RISK_SYSTEM_PROMPT

    def test_strategy_tree_not_in_bull_prompt(self) -> None:
        assert "Strategy selection decision tree" not in BULL_SYSTEM_PROMPT

    def test_strategy_tree_not_in_bear_prompt(self) -> None:
        assert "Strategy selection decision tree" not in BEAR_SYSTEM_PROMPT

    def test_appendix_content_matches_constant(self) -> None:
        """All three prompts contain the same appendix text."""
        assert PROMPT_RULES_APPENDIX in BULL_SYSTEM_PROMPT
        assert PROMPT_RULES_APPENDIX in BEAR_SYSTEM_PROMPT
        assert PROMPT_RULES_APPENDIX in RISK_SYSTEM_PROMPT

    def test_risk_strategy_tree_matches_constant(self) -> None:
        assert RISK_STRATEGY_TREE in RISK_SYSTEM_PROMPT


# --- Version header tests ---


class TestVersionHeaders:
    """Verify all agent modules have version header source comments."""

    def test_bull_source_has_v2_1_header(self) -> None:
        source = inspect.getsource(bull_module)
        assert "# VERSION: v2.1" in source

    def test_bear_source_has_v2_header(self) -> None:
        source = inspect.getsource(bear_module)
        assert "# VERSION: v2.0" in source

    def test_risk_source_has_v2_header(self) -> None:
        source = inspect.getsource(risk_module)
        assert "# VERSION: v2.0" in source


# --- build_cleaned_agent_response tests ---


class TestBuildCleanedAgentResponse:
    """Tests for the shared AgentResponse output validator helper."""

    def test_strips_think_tags_from_argument(
        self, agent_response_with_think_tags: AgentResponse
    ) -> None:
        result = build_cleaned_agent_response(agent_response_with_think_tags)
        assert "<think>" not in result.argument
        assert "</think>" not in result.argument
        assert "RSI at 62.3 is bullish." in result.argument

    def test_strips_think_tags_from_key_points(
        self, agent_response_with_think_tags: AgentResponse
    ) -> None:
        result = build_cleaned_agent_response(agent_response_with_think_tags)
        for point in result.key_points:
            assert "<think>" not in point
            assert "</think>" not in point

    def test_strips_think_tags_from_risks(
        self, agent_response_with_think_tags: AgentResponse
    ) -> None:
        result = build_cleaned_agent_response(agent_response_with_think_tags)
        for risk in result.risks_cited:
            assert "<think>" not in risk
            assert "</think>" not in risk

    def test_preserves_non_text_fields(
        self, agent_response_with_think_tags: AgentResponse
    ) -> None:
        result = build_cleaned_agent_response(agent_response_with_think_tags)
        assert result.agent_name == "bull"
        assert result.direction == SignalDirection.BULLISH
        assert result.confidence == 0.72
        assert result.model_used == "llama3.1:8b"

    def test_returns_original_when_no_tags(self, agent_response_clean: AgentResponse) -> None:
        result = build_cleaned_agent_response(agent_response_clean)
        assert result is agent_response_clean  # identity check — same object


# --- build_cleaned_trade_thesis tests ---


class TestBuildCleanedTradeThesis:
    """Tests for the shared TradeThesis output validator helper."""

    def test_strips_think_tags_from_summary(
        self, trade_thesis_with_think_tags: TradeThesis
    ) -> None:
        result = build_cleaned_trade_thesis(trade_thesis_with_think_tags)
        assert "<think>" not in result.summary
        assert "</think>" not in result.summary
        assert "Moderate bullish case." in result.summary

    def test_strips_think_tags_from_key_factors(
        self, trade_thesis_with_think_tags: TradeThesis
    ) -> None:
        result = build_cleaned_trade_thesis(trade_thesis_with_think_tags)
        for factor in result.key_factors:
            assert "<think>" not in factor
            assert "</think>" not in factor

    def test_strips_think_tags_from_risk_assessment(
        self, trade_thesis_with_think_tags: TradeThesis
    ) -> None:
        result = build_cleaned_trade_thesis(trade_thesis_with_think_tags)
        assert "<think>" not in result.risk_assessment
        assert "</think>" not in result.risk_assessment

    def test_preserves_non_text_fields(self, trade_thesis_with_think_tags: TradeThesis) -> None:
        result = build_cleaned_trade_thesis(trade_thesis_with_think_tags)
        assert result.ticker == "AAPL"
        assert result.direction == SignalDirection.BULLISH
        assert result.confidence == 0.65
        assert result.bull_score == 7.2
        assert result.bear_score == 4.5
        assert result.recommended_strategy is None

    def test_returns_original_when_no_tags(self, trade_thesis_clean: TradeThesis) -> None:
        result = build_cleaned_trade_thesis(trade_thesis_clean)
        assert result is trade_thesis_clean  # identity check — same object


# --- Volatility thesis fixtures ---


@pytest.fixture()
def vol_thesis_with_think_tags() -> VolatilityThesis:
    """VolatilityThesis with <think> tags in text fields.

    Note: iv_assessment is a VolAssessment StrEnum — think tags cannot appear
    there because Pydantic validation rejects non-enum values before the output
    validator runs.
    """
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation=("<think>rank analysis</think>IV rank at 85 is in the top 15%"),
        confidence=0.75,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="<think>strategy reasoning</think>High IV favors selling premium",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=[
            "<think>strike calc</think>185C",
            "<think>strike calc</think>195C",
        ],
        key_vol_factors=[
            "<think>factor</think>Earnings in 5 days",
            "<think>factor</think>IV rank 85",
        ],
        model_used="<think>model info</think>llama3.1:8b",
    )


@pytest.fixture()
def vol_thesis_clean() -> VolatilityThesis:
    """VolatilityThesis with no <think> tags."""
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85 is in the top 15%",
        confidence=0.75,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors selling premium",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["Earnings in 5 days", "IV rank 85"],
        model_used="llama3.1:8b",
    )


# --- build_cleaned_volatility_thesis tests ---


class TestBuildCleanedVolatilityThesis:
    """Tests for the shared VolatilityThesis output validator helper."""

    def test_iv_assessment_passes_through_as_enum(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        """iv_assessment is VolAssessment StrEnum — passes through unchanged."""
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        assert result.iv_assessment == vol_thesis_with_think_tags.iv_assessment

    def test_strips_think_tags_from_iv_rank_interpretation(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        assert "<think>" not in result.iv_rank_interpretation
        assert "</think>" not in result.iv_rank_interpretation
        assert "IV rank at 85" in result.iv_rank_interpretation

    def test_strips_think_tags_from_strategy_rationale(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        assert "<think>" not in result.strategy_rationale
        assert "</think>" not in result.strategy_rationale
        assert "High IV favors selling premium" in result.strategy_rationale

    def test_strips_think_tags_from_suggested_strikes(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        for strike in result.suggested_strikes:
            assert "<think>" not in strike
            assert "</think>" not in strike

    def test_strips_think_tags_from_key_vol_factors(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        for factor in result.key_vol_factors:
            assert "<think>" not in factor
            assert "</think>" not in factor

    def test_strips_think_tags_from_model_used(
        self, vol_thesis_with_think_tags: VolatilityThesis
    ) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        assert "<think>" not in result.model_used
        assert "</think>" not in result.model_used
        assert "llama3.1:8b" in result.model_used

    def test_preserves_non_text_fields(self, vol_thesis_with_think_tags: VolatilityThesis) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_with_think_tags)
        assert result.confidence == pytest.approx(0.75)
        assert result.recommended_strategy == SpreadType.IRON_CONDOR
        assert result.target_iv_entry == pytest.approx(85.0)
        assert result.target_iv_exit == pytest.approx(50.0)

    def test_returns_original_when_no_tags(self, vol_thesis_clean: VolatilityThesis) -> None:
        result = build_cleaned_volatility_thesis(vol_thesis_clean)
        assert result is vol_thesis_clean  # identity check — same object
