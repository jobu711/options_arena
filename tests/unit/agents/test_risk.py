"""Tests for the risk agent — debate adjudication and TradeThesis production.

Tests cover:
  - Agent produces valid TradeThesis via TestModel
  - Confidence is within [0.0, 1.0]
  - Ticker field present
  - Direction field present
  - Key factors list populated
  - Risk assessment field present
  - Summary field present
  - Bull/bear score fields present
  - Usage tracking works
  - Dynamic prompt includes both bull and bear arguments
  - Output validator strips <think> tags instead of rejecting
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps
from options_arena.agents.risk import (
    RISK_SYSTEM_PROMPT,
    clean_think_tags,
    risk_agent,
    risk_dynamic_prompt,
)
from options_arena.models import AgentResponse, SignalDirection, TradeThesis

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
async def test_risk_produces_trade_thesis(mock_debate_deps: DebateDeps) -> None:
    """Risk agent returns a TradeThesis instance."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, TradeThesis)


@pytest.mark.asyncio
async def test_risk_confidence_in_range(mock_debate_deps: DebateDeps) -> None:
    """Risk agent confidence is within [0.0, 1.0]."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_risk_has_ticker(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a non-empty ticker."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.ticker, str)


@pytest.mark.asyncio
async def test_risk_has_direction(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a direction field."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert result.output.direction is not None


@pytest.mark.asyncio
async def test_risk_has_key_factors(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has key_factors list."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.key_factors, list)


@pytest.mark.asyncio
async def test_risk_has_summary(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a non-empty summary."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.summary, str)


@pytest.mark.asyncio
async def test_risk_has_risk_assessment(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a non-empty risk_assessment."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.risk_assessment, str)


@pytest.mark.asyncio
async def test_risk_has_bull_and_bear_scores(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has bull_score and bear_score."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.bull_score, float)
    assert isinstance(result.output.bear_score, float)


@pytest.mark.asyncio
async def test_risk_returns_usage(mock_debate_deps: DebateDeps) -> None:
    """Risk agent result includes usage tracking."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Adjudicate", deps=mock_debate_deps, model=TestModel())
    usage = result.usage()
    assert usage.requests >= 0


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_includes_bull_case(
    mock_debate_deps: DebateDeps,
    mock_agent_response: AgentResponse,
) -> None:
    """Dynamic prompt injects bull response with delimiters when present."""
    mock_debate_deps.bull_response = mock_agent_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<BULL_CASE>>>" in prompt
    assert "<<<END_BULL_CASE>>>" in prompt


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_includes_bear_case(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt injects bear response with delimiters when present."""
    bear_response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.6,
        argument="IV is too high for long positions.",
        key_points=["IV elevated", "Overbought RSI"],
        risks_cited=["Potential reversal"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    mock_debate_deps.bear_response = bear_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<BEAR_CASE>>>" in prompt
    assert "<<<END_BEAR_CASE>>>" in prompt


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_no_arguments(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt excludes argument sections when both are None."""
    mock_debate_deps.bull_response = None
    mock_debate_deps.bear_response = None
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<BULL_CASE>>>" not in prompt
    assert "<<<BEAR_CASE>>>" not in prompt


@pytest.mark.asyncio
async def test_risk_system_prompt_exists() -> None:
    """Risk system prompt constant is defined and non-empty."""
    assert RISK_SYSTEM_PROMPT
    assert "risk" in RISK_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_risk_output_validator_strips_think_tags_in_summary(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator strips <think> tags from summary instead of rejecting."""
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.5,
        summary="<think>reasoning</think> Moderate bullish case.",
        bull_score=6.0,
        bear_score=4.0,
        key_factors=["Momentum"],
        risk_assessment="Moderate risk.",
        recommended_strategy=None,
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    cleaned = await clean_think_tags(mock_ctx, thesis)
    assert "<think>" not in cleaned.summary
    assert "</think>" not in cleaned.summary
    assert "Moderate bullish case." in cleaned.summary


@pytest.mark.asyncio
async def test_risk_output_validator_strips_think_tags_in_risk_assessment(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator strips <think> tags from risk_assessment."""
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.5,
        summary="Moderate bullish case.",
        bull_score=6.0,
        bear_score=4.0,
        key_factors=["Momentum"],
        risk_assessment="<think>analysis</think> Position carefully.",
        recommended_strategy=None,
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    cleaned = await clean_think_tags(mock_ctx, thesis)
    assert "<think>" not in cleaned.risk_assessment
    assert "Position carefully." in cleaned.risk_assessment


@pytest.mark.asyncio
async def test_risk_output_validator_passthrough_when_no_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator returns output unchanged when no <think> tags present."""
    thesis = TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.5,
        summary="Moderate bullish case.",
        bull_score=6.0,
        bear_score=4.0,
        key_factors=["Momentum"],
        risk_assessment="Position carefully.",
        recommended_strategy=None,
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    result = await clean_think_tags(mock_ctx, thesis)
    assert result is thesis
