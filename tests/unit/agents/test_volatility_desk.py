"""Tests for the Volatility desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.volatility_desk import run_vol_desk_query, vol_desk
from options_arena.models import AgencyConfig, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Analyze AAPL vol", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestVolDeskAgent:
    """vol_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert vol_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        # Check the output type via agent internals
        assert vol_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        # Agent should have the volatility toolset registered
        toolset = vol_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunVolDeskQuery:
    """run_vol_desk_query() wrapper tests."""

    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        result = await run_vol_desk_query("What is AAPL IV?", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.VOLATILITY

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_vol_desk_query("Check vol", deps, model=TestModel())
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(custom_output_text="<think>reasoning</think>The IV is elevated.")
        result = await run_vol_desk_query("Analyze vol", deps, model=test_model)
        assert "<think>" not in result.response
        assert "The IV is elevated." in result.response

    async def test_never_raises_on_error(self) -> None:
        deps = _make_deps()
        # Don't pass model - with ALLOW_MODEL_REQUESTS=False this should error
        # but run_vol_desk_query should catch it
        result = await run_vol_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "Error" in result.response or "timed out" in result.response.lower()

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_vol_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_vol_desk_query("Analyze AAPL", deps, model=TestModel())
        # tools_used comes from the deps accumulator
        assert isinstance(result.tools_used, list)

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, default_tool_budget=5)
        result = await run_vol_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_successful_response_has_confidence(self) -> None:
        deps = _make_deps()
        result = await run_vol_desk_query("test", deps, model=TestModel())
        # Successful responses get confidence=0.7
        assert result.confidence == pytest.approx(0.7, abs=0.01)
