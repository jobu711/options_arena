"""TestModel-based quality tests for all 8 debate agents.

Tests cover:
  - Each agent produces valid typed output via TestModel
  - Output types are correct (AgentResponse, VolatilityThesis, FlowThesis,
    FundamentalThesis, RiskAssessment, ContrarianThesis)
  - Confidence values are within [0.0, 1.0]

Uses ``models.ALLOW_MODEL_REQUESTS = False`` at module level to prevent
accidental real API calls in the test suite.
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps
from options_arena.agents.bear import bear_agent
from options_arena.agents.bull import bull_agent
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.risk import risk_agent
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    FlowThesis,
    FundamentalThesis,
    RiskAssessment,
    VolatilityThesis,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


@pytest.mark.asyncio
async def test_bull_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Bull agent returns an AgentResponse instance with valid confidence."""
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run(
            "Analyze AAPL bullish case", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, AgentResponse)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_bear_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Bear agent returns an AgentResponse instance with valid confidence."""
    with bear_agent.override(model=TestModel()):
        result = await bear_agent.run(
            "Analyze AAPL bearish case", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, AgentResponse)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_trend_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Trend agent returns an AgentResponse instance with valid confidence."""
    with trend_agent.override(model=TestModel()):
        result = await trend_agent.run(
            "Analyze AAPL trend", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, AgentResponse)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_volatility_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Volatility agent returns a VolatilityThesis instance with valid confidence."""
    with volatility_agent.override(model=TestModel()):
        result = await volatility_agent.run(
            "Analyze AAPL volatility", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, VolatilityThesis)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_flow_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Flow agent returns a FlowThesis instance with valid confidence."""
    with flow_agent.override(model=TestModel()):
        result = await flow_agent.run(
            "Analyze AAPL options flow", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, FlowThesis)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_fundamental_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Fundamental agent returns a FundamentalThesis instance with valid confidence."""
    with fundamental_agent.override(model=TestModel()):
        result = await fundamental_agent.run(
            "Analyze AAPL fundamentals", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, FundamentalThesis)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_risk_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Risk agent returns a RiskAssessment instance with valid confidence."""
    with risk_agent.override(model=TestModel()):
        result = await risk_agent.run("Assess AAPL risk", deps=mock_debate_deps, model=TestModel())
    assert isinstance(result.output, RiskAssessment)
    assert 0.0 <= result.output.confidence <= 1.0


@pytest.mark.asyncio
async def test_contrarian_produces_valid_output(mock_debate_deps: DebateDeps) -> None:
    """Contrarian agent returns a ContrarianThesis instance."""
    with contrarian_agent.override(model=TestModel()):
        result = await contrarian_agent.run(
            "Challenge AAPL consensus", deps=mock_debate_deps, model=TestModel()
        )
    assert isinstance(result.output, ContrarianThesis)
    assert 0.0 <= result.output.dissent_confidence <= 1.0
