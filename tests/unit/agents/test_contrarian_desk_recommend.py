"""Tests for the Contrarian desk recommendation agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.contrarian_desk import (
    contrarian_desk_recommend,
    run_contrarian_desk_recommendation,
)
from options_arena.models import AgencyConfig, DeskType
from options_arena.models.recommendation import ContrarianAssessment

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Challenge AAPL consensus", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestContrarianDeskRecommend:
    """contrarian_desk_recommend Agent instance tests."""

    def test_agent_exists(self) -> None:
        """Recommendation agent instance exists at module level."""
        assert contrarian_desk_recommend is not None

    def test_agent_output_type(self) -> None:
        """Output type is ContrarianAssessment."""
        assert contrarian_desk_recommend._output_type is ContrarianAssessment  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_produces_assessment(self) -> None:
        """Happy path: returns (ContrarianAssessment, RunUsage) tuple."""
        deps = _make_deps()
        with contrarian_desk_recommend.override(model=TestModel()):
            assessment, usage = await run_contrarian_desk_recommendation(deps, model=TestModel())
        assert isinstance(assessment, ContrarianAssessment)
        assert assessment.desk == DeskType.CONTRARIAN
        assert isinstance(usage, RunUsage)

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self) -> None:
        """Confidence is within [0.0, 1.0]."""
        deps = _make_deps()
        with contrarian_desk_recommend.override(model=TestModel()):
            assessment, _usage = await run_contrarian_desk_recommendation(deps, model=TestModel())
        assert 0.0 <= assessment.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_no_model_returns_fallback(self) -> None:
        """No model -> fallback with contrarian-specific fields."""
        deps = _make_deps()
        assessment, usage = await run_contrarian_desk_recommendation(deps)
        assert isinstance(assessment, ContrarianAssessment)
        assert assessment.desk == DeskType.CONTRARIAN
        assert assessment.confidence == pytest.approx(0.2)
        assert assessment.model_used == "data-driven-fallback"
        assert assessment.consensus_challenged is None
        assert assessment.contrarian_thesis is None
        assert isinstance(usage, RunUsage)

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self) -> None:
        """Timeout -> fallback assessment (never raises)."""
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)
        assessment, usage = await run_contrarian_desk_recommendation(
            deps, model=TestModel(), config=config
        )
        assert isinstance(assessment, ContrarianAssessment)
        assert isinstance(usage, RunUsage)

    @pytest.mark.asyncio
    async def test_tools_used_tracked(self) -> None:
        """tools_used list is populated from deps on fallback."""
        deps = _make_deps()
        deps.tools_used.append("fetch_quote")
        # Fallback path uses deps.tools_used
        assessment, _usage = await run_contrarian_desk_recommendation(deps)
        assert isinstance(assessment.tools_used, list)
        assert "fetch_quote" in assessment.tools_used

    @pytest.mark.asyncio
    async def test_fallback_returns_zero_usage(self) -> None:
        """Fallback paths return RunUsage() with zero tokens."""
        deps = _make_deps()
        _assessment, usage = await run_contrarian_desk_recommendation(deps)
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
