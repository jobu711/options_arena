"""Tests for the volatility agent — implied volatility assessment.

Tests cover:
  - Agent produces valid VolatilityThesis via TestModel
  - Confidence is within [0.0, 1.0]
  - IV assessment field present
  - Strategy rationale field present
  - Key vol factors list populated
  - Model used field present
  - Usage tracking works
  - Dynamic prompt includes bull/bear arguments when set
  - Dynamic prompt excludes arguments when not set
  - Output validator strips <think> tags instead of rejecting
  - Output validator passes through when no <think> tags present
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps, build_cleaned_volatility_thesis
from options_arena.agents.volatility import (
    VOLATILITY_SYSTEM_PROMPT,
    clean_think_tags,
    volatility_agent,
    volatility_dynamic_prompt,
)
from options_arena.models import SignalDirection, SpreadType, VolatilityThesis

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


def _build_test_model() -> TestModel:
    """Build a TestModel that produces a valid VolatilityThesis."""
    return TestModel(
        custom_output_args={
            "iv_assessment": "overpriced",
            "iv_rank_interpretation": "IV rank at 85 places current IV in top 15% of range",
            "confidence": 0.7,
            "recommended_strategy": "iron_condor",
            "strategy_rationale": "High IV rank favors selling premium via neutral strategies",
            "target_iv_entry": 85.0,
            "target_iv_exit": 50.0,
            "suggested_strikes": ["185C", "195C", "170P", "160P"],
            "key_vol_factors": ["Earnings in 5 days", "IV Rank at 85"],
            "model_used": "test-model",
        }
    )


@pytest.mark.asyncio
async def test_volatility_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent returns a VolatilityThesis instance."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert isinstance(result.output, VolatilityThesis)


@pytest.mark.asyncio
async def test_volatility_confidence_in_range(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent confidence is within [0.0, 1.0]."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_volatility_has_iv_assessment(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent output has a non-empty iv_assessment."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert result.output.iv_assessment


@pytest.mark.asyncio
async def test_volatility_has_strategy_rationale(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent output has a non-empty strategy_rationale."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert result.output.strategy_rationale


@pytest.mark.asyncio
async def test_volatility_has_key_vol_factors(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent output has key_vol_factors list."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert isinstance(result.output.key_vol_factors, list)


@pytest.mark.asyncio
async def test_volatility_has_model_used(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent output has a non-empty model_used string."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    assert isinstance(result.output.model_used, str)


@pytest.mark.asyncio
async def test_volatility_returns_usage(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent result includes usage tracking."""
    test_model = _build_test_model()
    with volatility_agent.override(model=test_model):
        result = await volatility_agent.run(
            "Assess IV for AAPL", deps=mock_debate_deps, model=test_model
        )
    usage = result.usage()
    assert usage.requests >= 0


@pytest.mark.asyncio
async def test_volatility_system_prompt_exists() -> None:
    """Volatility system prompt constant is defined and non-empty."""
    assert VOLATILITY_SYSTEM_PROMPT
    assert "volatility" in VOLATILITY_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_volatility_dynamic_prompt_includes_bull_argument(
    mock_debate_deps: DebateDeps,
    mock_agent_response: object,
) -> None:
    """Dynamic prompt injects bull_response argument with delimiters."""
    from options_arena.models import AgentResponse

    assert isinstance(mock_agent_response, AgentResponse)
    mock_debate_deps.bull_response = mock_agent_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await volatility_dynamic_prompt(mock_ctx)
    assert "<<<BULL_ARGUMENT>>>" in prompt
    assert mock_agent_response.argument in prompt
    assert "<<<END_BULL_ARGUMENT>>>" in prompt


@pytest.mark.asyncio
async def test_volatility_dynamic_prompt_includes_bear_argument(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt injects bear_response argument with delimiters."""
    from options_arena.models import AgentResponse

    bear_response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.6,
        argument="IV is elevated making premiums expensive.",
        key_points=["IV overpriced"],
        risks_cited=["Market reversal"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    mock_debate_deps.bear_response = bear_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await volatility_dynamic_prompt(mock_ctx)
    assert "<<<BEAR_ARGUMENT>>>" in prompt
    assert bear_response.argument in prompt
    assert "<<<END_BEAR_ARGUMENT>>>" in prompt


@pytest.mark.asyncio
async def test_volatility_dynamic_prompt_no_arguments(
    mock_debate_deps: DebateDeps,
) -> None:
    """Dynamic prompt excludes argument sections when no bull/bear responses."""
    mock_debate_deps.bull_response = None
    mock_debate_deps.bear_response = None
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await volatility_dynamic_prompt(mock_ctx)
    assert "<<<BULL_ARGUMENT>>>" not in prompt
    assert "<<<BEAR_ARGUMENT>>>" not in prompt


@pytest.mark.asyncio
async def test_volatility_dynamic_prompt_includes_both_arguments(
    mock_debate_deps: DebateDeps,
    mock_agent_response: object,
) -> None:
    """Dynamic prompt injects both bull and bear arguments when both set."""
    from options_arena.models import AgentResponse

    assert isinstance(mock_agent_response, AgentResponse)
    bear_response = AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="RSI overbought at 72.",
        key_points=["RSI overbought"],
        risks_cited=["Earnings risk"],
        contracts_referenced=["AAPL $190 CALL"],
        model_used="test",
    )
    mock_debate_deps.bull_response = mock_agent_response
    mock_debate_deps.bear_response = bear_response
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    prompt = await volatility_dynamic_prompt(mock_ctx)
    assert "<<<BULL_ARGUMENT>>>" in prompt
    assert "<<<END_BULL_ARGUMENT>>>" in prompt
    assert "<<<BEAR_ARGUMENT>>>" in prompt
    assert "<<<END_BEAR_ARGUMENT>>>" in prompt


@pytest.mark.asyncio
async def test_volatility_output_validator_strips_think_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator strips <think> tags from text fields instead of rejecting."""
    thesis = VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="<think>reasoning</think> IV rank at 85 is elevated.",
        confidence=0.7,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="<think>more reasoning</think> Sell premium via iron condor.",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["<think>factor analysis</think> Earnings in 5 days"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    cleaned = await clean_think_tags(mock_ctx, thesis)
    assert "<think>" not in cleaned.iv_rank_interpretation
    assert "</think>" not in cleaned.iv_rank_interpretation
    assert "IV rank at 85 is elevated." in cleaned.iv_rank_interpretation
    assert "<think>" not in cleaned.strategy_rationale
    assert "Sell premium via iron condor." in cleaned.strategy_rationale
    assert all("<think>" not in f for f in cleaned.key_vol_factors)


@pytest.mark.asyncio
async def test_volatility_output_validator_passthrough_when_no_tags(
    mock_debate_deps: DebateDeps,
) -> None:
    """Output validator returns output unchanged when no <think> tags present."""
    thesis = VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85 is elevated.",
        confidence=0.7,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="Sell premium via iron condor.",
        target_iv_entry=85.0,
        target_iv_exit=50.0,
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["Earnings in 5 days"],
        model_used="test",
    )
    mock_ctx = MagicMock()
    mock_ctx.deps = mock_debate_deps
    result = await clean_think_tags(mock_ctx, thesis)
    assert result is thesis  # same object — no copy needed


@pytest.mark.asyncio
async def test_build_cleaned_volatility_thesis_strips_all_fields() -> None:
    """Shared helper strips <think> tags from all text fields."""
    thesis = VolatilityThesis(
        iv_assessment="<think>assess</think>overpriced",
        iv_rank_interpretation="<think>interp</think>IV rank high",
        confidence=0.65,
        recommended_strategy=None,
        strategy_rationale="<think>rat</think>No trade warranted.",
        target_iv_entry=None,
        target_iv_exit=None,
        suggested_strikes=["<think>s</think>185C"],
        key_vol_factors=["<think>f</think>Earnings soon"],
        model_used="<think>m</think>llama3.1:8b",
    )
    cleaned = build_cleaned_volatility_thesis(thesis)
    assert "<think>" not in cleaned.iv_assessment
    assert "<think>" not in cleaned.iv_rank_interpretation
    assert "<think>" not in cleaned.strategy_rationale
    assert all("<think>" not in s for s in cleaned.suggested_strikes)
    assert all("<think>" not in f for f in cleaned.key_vol_factors)
    assert "<think>" not in cleaned.model_used
    # Confidence and numeric fields preserved
    assert cleaned.confidence == pytest.approx(0.65, abs=0.01)
    assert cleaned.recommended_strategy is None
