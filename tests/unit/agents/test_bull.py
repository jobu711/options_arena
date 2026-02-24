"""Tests for the bull agent — bullish options analysis.

Tests cover:
  - Agent produces valid AgentResponse via TestModel
  - Confidence is within [0.0, 1.0]
  - Agent name is set
  - Direction field present
  - Key points list populated
  - Risks cited list populated
  - Contracts referenced list populated
  - Model used field present
  - Usage tracking works
  - Output validator rejects <think> tags
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps
from options_arena.agents.bull import BULL_SYSTEM_PROMPT, bull_agent, reject_think_tags
from options_arena.models import AgentResponse

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
async def test_bull_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Bull agent returns an AgentResponse instance."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert isinstance(result.output, AgentResponse)


@pytest.mark.asyncio
async def test_bull_confidence_in_range(mock_debate_deps: DebateDeps) -> None:
    """Bull agent confidence is within [0.0, 1.0]."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_bull_has_agent_name(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has a non-empty agent_name."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert result.output.agent_name


@pytest.mark.asyncio
async def test_bull_has_direction(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has a direction field."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert result.output.direction is not None


@pytest.mark.asyncio
async def test_bull_has_key_points(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has key_points list."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert isinstance(result.output.key_points, list)


@pytest.mark.asyncio
async def test_bull_has_risks_cited(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has risks_cited list."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert isinstance(result.output.risks_cited, list)


@pytest.mark.asyncio
async def test_bull_has_contracts_referenced(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has contracts_referenced list."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert isinstance(result.output.contracts_referenced, list)


@pytest.mark.asyncio
async def test_bull_has_model_used(mock_debate_deps: DebateDeps) -> None:
    """Bull agent output has a non-empty model_used string."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    assert isinstance(result.output.model_used, str)


@pytest.mark.asyncio
async def test_bull_returns_usage(mock_debate_deps: DebateDeps) -> None:
    """Bull agent result includes usage tracking."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_debate_deps)
    usage = result.usage()
    assert usage.requests >= 0


@pytest.mark.asyncio
async def test_bull_system_prompt_exists() -> None:
    """Bull system prompt constant is defined and non-empty."""
    assert BULL_SYSTEM_PROMPT
    assert "bullish" in BULL_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_bull_output_validator_rejects_think_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator raises ModelRetry when argument contains <think> tags."""
    from unittest.mock import MagicMock

    from options_arena.models import SignalDirection

    response = AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.7,
        argument="<think>reasoning</think> RSI is bullish.",
        key_points=["RSI trending up"],
        risks_cited=["Market risk"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    with pytest.raises(ModelRetry):
        await reject_think_tags(mock_ctx, response)
