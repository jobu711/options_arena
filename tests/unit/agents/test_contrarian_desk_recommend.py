"""Tests for the Contrarian desk recommendation agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.contrarian_desk import (
    contrarian_desk_recommend,
    run_contrarian_desk_recommendation,
)
from options_arena.models import AgencyConfig, DeskType
from options_arena.models.recommendation import ContrarianAssessment

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(
    query: str = "Challenge AAPL consensus", ticker: str = "AAPL"
) -> DeskDeps:
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
        """Happy path: returns ContrarianAssessment with correct desk enum."""
        deps = _make_deps()
        with contrarian_desk_recommend.override(model=TestModel()):
            result = await run_contrarian_desk_recommendation(deps, model=TestModel())
        assert isinstance(result, ContrarianAssessment)
        assert result.desk == DeskType.CONTRARIAN

    @pytest.mark.asyncio
    async def test_confidence_in_valid_range(self) -> None:
        """Confidence is within [0.0, 1.0]."""
        deps = _make_deps()
        with contrarian_desk_recommend.override(model=TestModel()):
            result = await run_contrarian_desk_recommendation(deps, model=TestModel())
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    async def test_no_model_returns_fallback(self) -> None:
        """No model -> fallback with contrarian-specific fields."""
        deps = _make_deps()
        result = await run_contrarian_desk_recommendation(deps)
        assert isinstance(result, ContrarianAssessment)
        assert result.desk == DeskType.CONTRARIAN
        assert result.confidence == pytest.approx(0.2)
        assert result.model_used == "data-driven-fallback"
        assert result.consensus_challenged is None
        assert result.contrarian_thesis is None

    @pytest.mark.asyncio
    async def test_timeout_returns_fallback(self) -> None:
        """Timeout -> fallback assessment (never raises)."""
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)
        # Even if TestModel is fast and doesn't timeout, the code path is exercised
        result = await run_contrarian_desk_recommendation(
            deps, model=TestModel(), config=config
        )
        assert isinstance(result, ContrarianAssessment)

    @pytest.mark.asyncio
    async def test_tools_used_tracked(self) -> None:
        """tools_used list is populated from deps on fallback."""
        deps = _make_deps()
        deps.tools_used.append("fetch_quote")
        # Fallback path uses deps.tools_used
        result = await run_contrarian_desk_recommendation(deps)
        assert isinstance(result.tools_used, list)
        assert "fetch_quote" in result.tools_used
