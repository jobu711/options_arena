"""Tests for the Flow desk recommendation agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.flow_desk import (
    flow_desk_recommend,
    run_flow_desk_recommendation,
)
from options_arena.models import AgencyConfig, DeskType, SignalDirection
from options_arena.models.recommendation import FlowAssessment

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=f"Analyze {ticker} flow",
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestFlowDeskRecommendAgent:
    """flow_desk_recommend Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert flow_desk_recommend is not None

    def test_agent_output_type(self) -> None:
        assert flow_desk_recommend._output_type is FlowAssessment  # noqa: SLF001


@pytest.mark.asyncio
class TestRunFlowDeskRecommendation:
    """run_flow_desk_recommendation() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_assessment(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_recommendation(deps, model=TestModel())
        assert isinstance(result, FlowAssessment)
        assert result.desk == DeskType.FLOW

    async def test_confidence_in_valid_range(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_recommendation(deps, model=TestModel())
        assert 0.0 <= result.confidence <= 1.0

    async def test_no_model_returns_fallback(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_recommendation(deps)
        assert isinstance(result, FlowAssessment)
        assert result.confidence <= 0.3
        assert result.direction == SignalDirection.NEUTRAL
        assert result.model_used == "data-driven-fallback"

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)
        result = await run_flow_desk_recommendation(
            deps,
            model=TestModel(),
            config=config,
        )
        assert isinstance(result, FlowAssessment)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_recommendation(deps, model=TestModel())
        assert isinstance(result.tools_used, list)

    async def test_fallback_has_correct_ticker(self) -> None:
        deps = _make_deps(ticker="TSLA")
        result = await run_flow_desk_recommendation(deps)
        assert "TSLA" in result.summary

    async def test_model_settings_accepted(self) -> None:
        from pydantic_ai.settings import ModelSettings

        deps = _make_deps()
        settings = ModelSettings(temperature=0.5)
        result = await run_flow_desk_recommendation(
            deps,
            model=TestModel(),
            model_settings=settings,
        )
        assert isinstance(result, FlowAssessment)
