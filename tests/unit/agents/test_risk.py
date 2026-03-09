"""Tests for the risk agent — RiskAssessment production and dynamic prompt.

Tests cover:
  - Agent produces valid RiskAssessment via TestModel
  - Confidence is within [0.0, 1.0]
  - Key risks list populated
  - Risk level field present
  - Max loss estimate field present
  - Usage tracking works
  - Dynamic prompt includes Phase 1 agent outputs (trend, volatility, flow, fundamental)
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
    clean_risk_think_tags,
    risk_agent,
    risk_dynamic_prompt,
)
from options_arena.models import (
    AgentResponse,
    RiskAssessment,
    RiskLevel,
    VolatilityThesis,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
async def test_risk_produces_risk_assessment(mock_debate_deps: DebateDeps) -> None:
    """Risk agent returns a RiskAssessment instance."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, RiskAssessment)


@pytest.mark.asyncio
async def test_risk_confidence_in_range(mock_debate_deps: DebateDeps) -> None:
    """Risk agent confidence is within [0.0, 1.0]."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_risk_has_risk_level(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a risk_level field."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.risk_level, RiskLevel)


@pytest.mark.asyncio
async def test_risk_has_key_risks(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has key_risks list."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.key_risks, list)


@pytest.mark.asyncio
async def test_risk_has_max_loss_estimate(mock_debate_deps: DebateDeps) -> None:
    """Risk agent output has a non-empty max_loss_estimate."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output.max_loss_estimate, str)


@pytest.mark.asyncio
async def test_risk_returns_usage(mock_debate_deps: DebateDeps) -> None:
    """Risk agent result includes usage tracking."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess risk", deps=mock_debate_deps, model=TestModel())
    usage = result.usage()
    assert usage.requests >= 0


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_includes_trend(
    mock_debate_deps: DebateDeps,
    mock_agent_response: AgentResponse,
) -> None:
    """Dynamic prompt injects trend output with delimiters when present."""
    mock_debate_deps.trend_response = mock_agent_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<TREND_AGENT>>>" in prompt
    assert "<<<END_TREND_AGENT>>>" in prompt


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_includes_volatility(
    mock_debate_deps: DebateDeps,
    mock_volatility_thesis: VolatilityThesis,
) -> None:
    """Dynamic prompt injects volatility output with delimiters when present."""
    mock_debate_deps.volatility_thesis = mock_volatility_thesis
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<VOLATILITY_AGENT>>>" in prompt
    assert "<<<END_VOLATILITY_AGENT>>>" in prompt
    assert "IV Assessment: overpriced" in prompt
    assert "Confidence: 0.75" in prompt
    assert "Strategy Rationale: High IV favors selling premium via iron condor." in prompt
    assert "Recommended Strategy: iron_condor" in prompt
    assert "Key Volatility Factors: Earnings in 5 days, IV rank 85" in prompt


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_no_phase1_outputs(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt excludes agent sections when all Phase 1 outputs are None."""
    mock_debate_deps.trend_response = None
    mock_debate_deps.volatility_thesis = None
    mock_debate_deps.flow_thesis = None
    mock_debate_deps.fundamental_thesis = None
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<TREND_AGENT>>>" not in prompt
    assert "<<<VOLATILITY_AGENT>>>" not in prompt
    assert "<<<FLOW_AGENT>>>" not in prompt
    assert "<<<FUNDAMENTAL_AGENT>>>" not in prompt


@pytest.mark.asyncio
async def test_risk_system_prompt_exists() -> None:
    """Risk system prompt constant is defined and non-empty."""
    assert RISK_SYSTEM_PROMPT
    assert "risk" in RISK_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_risk_output_validator_strips_think_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator strips <think> tags from max_loss_estimate."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.6,
        max_loss_estimate="<think>calculating</think> $480 per contract.",
        key_risks=["Earnings risk"],
        risk_mitigants=["Defined risk"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    cleaned = await clean_risk_think_tags(mock_ctx, assessment)
    assert "<think>" not in cleaned.max_loss_estimate
    assert "</think>" not in cleaned.max_loss_estimate
    assert "$480 per contract." in cleaned.max_loss_estimate


@pytest.mark.asyncio
async def test_risk_output_validator_passthrough_when_no_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator returns output unchanged when no <think> tags present."""
    assessment = RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.6,
        max_loss_estimate="$480 per contract.",
        key_risks=["Earnings risk"],
        risk_mitigants=["Defined risk"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    result = await clean_risk_think_tags(mock_ctx, assessment)
    assert result is assessment


@pytest.mark.asyncio
async def test_risk_dynamic_prompt_volatility_no_strategy(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt shows 'none' when vol recommended_strategy is None."""
    vol_thesis = VolatilityThesis(
        iv_assessment="fair",
        iv_rank_interpretation="IV rank at 45 is near the median.",
        confidence=0.5,
        recommended_strategy=None,
        strategy_rationale="No vol play warranted at current levels.",
        suggested_strikes=[],
        key_vol_factors=["IV near historical median"],
        model_used="test",
    )
    mock_debate_deps.volatility_thesis = vol_thesis
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await risk_dynamic_prompt(mock_ctx)
    assert "<<<VOLATILITY_AGENT>>>" in prompt
    assert "Recommended Strategy: none" in prompt
