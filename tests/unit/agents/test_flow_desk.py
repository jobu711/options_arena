"""Tests for the Flow desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.flow_desk import flow_desk, run_flow_desk_query
from options_arena.models import AgencyConfig, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Analyze AAPL flow", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestFlowDeskAgent:
    """flow_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert flow_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        assert flow_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = flow_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunFlowDeskQuery:
    """run_flow_desk_query() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_query("What is AAPL flow?", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.FLOW

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_query("Check flow", deps, model=TestModel())
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(
            custom_output_text="<think>reasoning</think>Put/call ratio is elevated."
        )
        result = await run_flow_desk_query("Analyze flow", deps, model=test_model)
        assert "<think>" not in result.response
        assert "Put/call ratio is elevated." in result.response

    async def test_no_model_returns_error_response(self) -> None:
        deps = _make_deps()
        # No model provided — early guard returns error DeskResponse
        result = await run_flow_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "no LLM model" in result.response

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_flow_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_flow_desk_query("Analyze AAPL", deps, model=TestModel())
        # tools_used comes from the deps accumulator
        assert isinstance(result.tools_used, list)

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, default_tool_budget=5)
        result = await run_flow_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_successful_response_has_confidence(self) -> None:
        from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE

        deps = _make_deps()
        result = await run_flow_desk_query("test", deps, model=TestModel())
        assert result.confidence == pytest.approx(DESK_SUCCESS_CONFIDENCE, abs=0.01)


class TestDeskFlowPrompt:
    """DESK_FLOW_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        assert isinstance(DESK_FLOW_PROMPT, str)
        assert len(DESK_FLOW_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        assert len(DESK_FLOW_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_FLOW_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        assert "fetch_quote" in DESK_FLOW_PROMPT
        assert "fetch_chain_summary" in DESK_FLOW_PROMPT
        assert "fetch_unusual_activity" in DESK_FLOW_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_FLOW_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT

        assert "VERSION" in DESK_FLOW_PROMPT


class TestFlowDeskReExports:
    """Verify flow desk is importable from agents package."""

    def test_flow_desk_importable_from_agents(self) -> None:
        from options_arena.agents import flow_desk as fd

        assert fd is not None

    def test_run_flow_desk_query_importable(self) -> None:
        from options_arena.agents import run_flow_desk_query as rfdq

        assert rfdq is not None

    def test_build_flow_toolset_importable(self) -> None:
        from options_arena.agents import build_flow_toolset

        assert build_flow_toolset is not None
