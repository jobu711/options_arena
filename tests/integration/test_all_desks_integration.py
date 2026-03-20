"""Integration tests for all 7 desk agents.

Verifies each desk produces a valid DeskResponse via TestModel, and that
run_agency_query routes to implemented desks without crashing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._routing import run_agency_query
from options_arena.agents.contrarian_desk import run_contrarian_desk_query
from options_arena.agents.flow_desk import run_flow_desk_query
from options_arena.agents.fundamental_desk import run_fundamental_desk_query
from options_arena.agents.research_desk import run_research_desk_query
from options_arena.agents.risk_desk import run_risk_desk_query
from options_arena.agents.trend_desk import run_trend_desk_query
from options_arena.agents.volatility_desk import run_vol_desk_query
from options_arena.models import AgencyConfig, AgencyQuery, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query="test query",
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


@pytest.mark.asyncio
class TestAllDesksIntegration:
    """Verify each of the 7 desks produces a valid DeskResponse via TestModel."""

    @pytest.mark.critical
    async def test_volatility_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_vol_desk_query("vol test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.VOLATILITY
        assert result.confidence > 0.0

    async def test_risk_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_risk_desk_query("risk test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.RISK

    async def test_trend_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_trend_desk_query("trend test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.TREND
        assert result.confidence > 0.0

    async def test_flow_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_query("flow test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.FLOW

    async def test_fundamental_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_fundamental_desk_query("earnings test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.FUNDAMENTAL

    async def test_contrarian_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_contrarian_desk_query("contrarian test", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.CONTRARIAN

    async def test_research_desk_responds(self) -> None:
        deps = _make_deps()
        result = await run_research_desk_query(
            "research test", deps, model=TestModel(call_tools=[])
        )
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.RESEARCH
        assert result.confidence > 0.0

    async def test_agency_query_dispatches_to_all_implemented(self) -> None:
        """run_agency_query routes to implemented desks without raising."""
        query = AgencyQuery(
            query_id="test-all-desks",
            query_text="What is the AAPL trend?",
            created_at=datetime.now(UTC),
        )
        result = await run_agency_query(
            query,
            market_data=MagicMock(),
            options_data=MagicMock(),
            fred=MagicMock(),
            repo=MagicMock(),
            model=None,  # Will get "no model" error responses but won't crash
            config=AgencyConfig(),
        )
        assert result is not None
        assert len(result.desk_responses) > 0

    async def test_all_desks_have_consistent_response_shape(self) -> None:
        """All desk responses have the same field structure."""
        runners: list[tuple[object, DeskType]] = [
            (run_vol_desk_query, DeskType.VOLATILITY),
            (run_risk_desk_query, DeskType.RISK),
            (run_trend_desk_query, DeskType.TREND),
            (run_flow_desk_query, DeskType.FLOW),
            (run_fundamental_desk_query, DeskType.FUNDAMENTAL),
            (run_contrarian_desk_query, DeskType.CONTRARIAN),
        ]
        for runner, expected_desk in runners:
            deps = _make_deps()
            result = await runner("test", deps, model=TestModel())  # type: ignore[operator]
            assert isinstance(result, DeskResponse)
            assert result.desk == expected_desk
            assert isinstance(result.response, str)
            assert isinstance(result.tools_used, list)
            assert isinstance(result.confidence, float)

    async def test_research_desk_consistent_response_shape(self) -> None:
        """Research desk has the same response shape (separate due to call_tools=[])."""
        deps = _make_deps()
        result = await run_research_desk_query("test", deps, model=TestModel(call_tools=[]))
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.RESEARCH
        assert isinstance(result.response, str)
        assert isinstance(result.tools_used, list)
        assert isinstance(result.confidence, float)
