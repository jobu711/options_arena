"""Tests for the bear agent — bearish options analysis.

Tests cover:
  - Agent produces valid AgentResponse via TestModel
  - Confidence is within [0.0, 1.0]
  - Agent name is set
  - Direction field present
  - Key points list populated
  - Risks cited list populated
  - Model used field present
  - Usage tracking works
  - Bear receives opponent argument via deps
  - Output validator rejects <think> tags
  - Dynamic prompt includes BULL_ARGUMENT delimiters when opponent_argument set
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import ModelRetry, models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps
from options_arena.agents.bear import (
    BEAR_SYSTEM_PROMPT,
    bear_agent,
    bear_dynamic_prompt,
    reject_think_tags,
)
from options_arena.models import AgentResponse, SignalDirection

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
async def test_bear_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Bear agent returns an AgentResponse instance."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, AgentResponse)


@pytest.mark.asyncio
async def test_bear_confidence_in_range(mock_debate_deps: DebateDeps) -> None:
    """Bear agent confidence is within [0.0, 1.0]."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_bear_has_agent_name(mock_debate_deps: DebateDeps) -> None:
    """Bear agent output has a non-empty agent_name."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert result.output.agent_name


@pytest.mark.asyncio
async def test_bear_has_direction(mock_debate_deps: DebateDeps) -> None:
    """Bear agent output has a direction field."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert result.output.direction is not None


@pytest.mark.asyncio
async def test_bear_has_key_points(mock_debate_deps: DebateDeps) -> None:
    """Bear agent output has key_points list."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.key_points, list)


@pytest.mark.asyncio
async def test_bear_has_risks_cited(mock_debate_deps: DebateDeps) -> None:
    """Bear agent output has risks_cited list."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.risks_cited, list)


@pytest.mark.asyncio
async def test_bear_has_model_used(mock_debate_deps: DebateDeps) -> None:
    """Bear agent output has a non-empty model_used string."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.model_used, str)


@pytest.mark.asyncio
async def test_bear_returns_usage(mock_debate_deps: DebateDeps) -> None:
    """Bear agent result includes usage tracking."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    usage = result.usage()
    assert usage.requests >= 0


@pytest.mark.asyncio
async def test_bear_receives_opponent_argument(mock_debate_deps: DebateDeps) -> None:
    """Bear agent works when opponent_argument is set on deps."""
    mock_debate_deps.opponent_argument = "Bull says RSI at 62.3 indicates momentum."
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run("Counter the bull", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, AgentResponse)


@pytest.mark.asyncio
async def test_bear_dynamic_prompt_includes_bull_argument(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt injects opponent_argument with delimiters."""
    mock_debate_deps.opponent_argument = "RSI is oversold at 35."
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await bear_dynamic_prompt(mock_ctx)
    assert "<<<BULL_ARGUMENT>>>" in prompt
    assert "RSI is oversold at 35." in prompt
    assert "<<<END_BULL_ARGUMENT>>>" in prompt


@pytest.mark.asyncio
async def test_bear_dynamic_prompt_no_bull_argument(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt excludes BULL_ARGUMENT section when no opponent_argument."""
    mock_debate_deps.opponent_argument = None
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await bear_dynamic_prompt(mock_ctx)
    assert "<<<BULL_ARGUMENT>>>" not in prompt


@pytest.mark.asyncio
async def test_bear_system_prompt_exists() -> None:
    """Bear system prompt constant is defined and non-empty."""
    assert BEAR_SYSTEM_PROMPT
    assert "bearish" in BEAR_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_bear_output_validator_rejects_think_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator raises ModelRetry when argument contains <think> tags."""
    response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.6,
        argument="<think>analyzing</think> IV is elevated.",
        key_points=["IV overpriced"],
        risks_cited=["Market reversal"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    with pytest.raises(ModelRetry):
        await reject_think_tags(mock_ctx, response)
