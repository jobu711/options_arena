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
)
from options_arena.agents.bear import BEAR_SYSTEM_PROMPT
from options_arena.agents.bull import BULL_SYSTEM_PROMPT
from options_arena.agents.risk import RISK_STRATEGY_TREE, RISK_SYSTEM_PROMPT
from options_arena.models import AgentResponse, SignalDirection, TradeThesis

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
    """Verify all agent modules have # VERSION: v2.0 source comments."""

    def test_bull_source_has_v2_header(self) -> None:
        source = inspect.getsource(bull_module)
        assert "# VERSION: v2.0" in source

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
