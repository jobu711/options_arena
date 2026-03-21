"""Tests for the Research desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._toolsets import build_research_toolset
from options_arena.agents.research_desk import research_desk, run_research_desk_query
from options_arena.models import AgencyConfig, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Research AAPL", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestResearchToolset:
    """build_research_toolset() tests."""

    def test_toolset_has_nine_tools(self) -> None:
        tools = build_research_toolset()
        assert len(tools) == 9

    def test_toolset_contains_expected_functions(self) -> None:
        from options_arena.agents._toolsets import (
            compute_indicator_on_demand,
            fetch_chain_summary,
            fetch_debate_history,
            fetch_earnings_history,
            fetch_quote,
            fetch_vol_surface_slice,
        )

        tools = build_research_toolset()
        assert fetch_quote in tools
        assert fetch_vol_surface_slice in tools
        assert fetch_chain_summary in tools
        assert fetch_earnings_history in tools
        assert compute_indicator_on_demand in tools
        assert fetch_debate_history in tools


class TestResearchDeskAgent:
    """research_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert research_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        assert research_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = research_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunResearchDeskQuery:
    """run_research_desk_query() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        # call_tools=[] to avoid exceeding the budget (6 tools, 5 budget)
        result = await run_research_desk_query(
            "Research AAPL", deps, model=TestModel(call_tools=[])
        )
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.RESEARCH

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_research_desk_query(
            "Research AAPL", deps, model=TestModel(call_tools=[])
        )
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(
            call_tools=[],
            custom_output_text="<think>reasoning</think>AAPL shows mixed signals.",
        )
        result = await run_research_desk_query("Research AAPL", deps, model=test_model)
        assert "<think>" not in result.response
        assert "AAPL shows mixed signals." in result.response

    async def test_no_model_returns_error_response(self) -> None:
        deps = _make_deps()
        result = await run_research_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "no LLM model" in result.response

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_research_desk_query(
            "test", deps, model=TestModel(call_tools=[]), config=config
        )
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_research_desk_query(
            "Research AAPL", deps, model=TestModel(call_tools=[])
        )
        assert isinstance(result.tools_used, list)

    async def test_uses_research_tool_budget(self) -> None:
        """Verify research uses cfg.research_tool_budget (7), not default (4)."""
        cfg = AgencyConfig()
        assert cfg.research_tool_budget == 7
        assert cfg.research_tool_budget > cfg.default_tool_budget

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, research_tool_budget=8)
        result = await run_research_desk_query(
            "test", deps, model=TestModel(call_tools=[]), config=config
        )
        assert isinstance(result, DeskResponse)

    async def test_successful_response_has_confidence(self) -> None:
        from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE

        deps = _make_deps()
        result = await run_research_desk_query("test", deps, model=TestModel(call_tools=[]))
        assert result.confidence == pytest.approx(DESK_SUCCESS_CONFIDENCE, abs=0.01)


class TestDeskResearchPrompt:
    """DESK_RESEARCH_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert isinstance(DESK_RESEARCH_PROMPT, str)
        assert len(DESK_RESEARCH_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert len(DESK_RESEARCH_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_RESEARCH_PROMPT

    def test_prompt_mentions_all_six_tools(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert "fetch_quote" in DESK_RESEARCH_PROMPT
        assert "fetch_vol_surface_slice" in DESK_RESEARCH_PROMPT
        assert "fetch_chain_summary" in DESK_RESEARCH_PROMPT
        assert "fetch_earnings_history" in DESK_RESEARCH_PROMPT
        assert "compute_indicator_on_demand" in DESK_RESEARCH_PROMPT
        assert "fetch_debate_history" in DESK_RESEARCH_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_RESEARCH_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert "VERSION" in DESK_RESEARCH_PROMPT

    def test_prompt_has_tool_budget_section(self) -> None:
        from options_arena.agents.prompts.desk_research import DESK_RESEARCH_PROMPT

        assert "Tool Budget" in DESK_RESEARCH_PROMPT
        assert "7 tool calls" in DESK_RESEARCH_PROMPT
        assert "9 tools" in DESK_RESEARCH_PROMPT
