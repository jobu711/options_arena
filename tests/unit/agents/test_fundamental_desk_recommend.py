"""Tests for the Fundamental desk recommendation agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.fundamental_desk import (
    fundamental_desk_recommend,
    run_fundamental_desk_recommendation,
)
from options_arena.models import AgencyConfig, DeskType, SignalDirection
from options_arena.models.recommendation import FundamentalAssessment

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=f"Analyze {ticker} fundamentals",
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestFundamentalDeskRecommendAgent:
    """fundamental_desk_recommend Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert fundamental_desk_recommend is not None

    def test_agent_output_type(self) -> None:
        assert fundamental_desk_recommend._output_type is FundamentalAssessment  # noqa: SLF001


@pytest.mark.asyncio
class TestRunFundamentalDeskRecommendation:
    """run_fundamental_desk_recommendation() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_assessment(self) -> None:
        deps = _make_deps()
        result = await run_fundamental_desk_recommendation(deps, model=TestModel())
        assert isinstance(result, FundamentalAssessment)
        assert result.desk == DeskType.FUNDAMENTAL

    async def test_confidence_in_valid_range(self) -> None:
        deps = _make_deps()
        result = await run_fundamental_desk_recommendation(deps, model=TestModel())
        assert 0.0 <= result.confidence <= 1.0

    async def test_no_model_returns_fallback(self) -> None:
        deps = _make_deps()
        result = await run_fundamental_desk_recommendation(deps)
        assert isinstance(result, FundamentalAssessment)
        assert result.confidence <= 0.3
        assert result.direction == SignalDirection.NEUTRAL
        assert result.model_used == "data-driven-fallback"

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)
        result = await run_fundamental_desk_recommendation(
            deps,
            model=TestModel(),
            config=config,
        )
        assert isinstance(result, FundamentalAssessment)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_fundamental_desk_recommendation(deps, model=TestModel())
        assert isinstance(result.tools_used, list)

    async def test_fallback_has_correct_ticker(self) -> None:
        deps = _make_deps(ticker="TSLA")
        result = await run_fundamental_desk_recommendation(deps)
        assert "TSLA" in result.summary

    async def test_model_settings_accepted(self) -> None:
        from pydantic_ai.settings import ModelSettings

        deps = _make_deps()
        settings = ModelSettings(temperature=0.5)
        result = await run_fundamental_desk_recommendation(
            deps,
            model=TestModel(),
            model_settings=settings,
        )
        assert isinstance(result, FundamentalAssessment)
