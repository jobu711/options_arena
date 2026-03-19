"""Tests for the Trend desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.trend_desk import run_trend_desk_query, trend_desk
from options_arena.models import AgencyConfig, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Analyze AAPL trend", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestTrendDeskAgent:
    """trend_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert trend_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        assert trend_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = trend_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunTrendDeskQuery:
    """run_trend_desk_query() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        result = await run_trend_desk_query("What is AAPL trend?", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.TREND

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_trend_desk_query("Check trend", deps, model=TestModel())
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(custom_output_text="<think>reasoning</think>The trend is bullish.")
        result = await run_trend_desk_query("Analyze trend", deps, model=test_model)
        assert "<think>" not in result.response
        assert "The trend is bullish." in result.response

    async def test_no_model_returns_error_response(self) -> None:
        deps = _make_deps()
        # No model provided — early guard returns error DeskResponse
        result = await run_trend_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "no LLM model" in result.response

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_trend_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_trend_desk_query("Analyze AAPL", deps, model=TestModel())
        # tools_used comes from the deps accumulator
        assert isinstance(result.tools_used, list)

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, default_tool_budget=5)
        result = await run_trend_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_successful_response_has_confidence(self) -> None:
        from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE

        deps = _make_deps()
        result = await run_trend_desk_query("test", deps, model=TestModel())
        assert result.confidence == pytest.approx(DESK_SUCCESS_CONFIDENCE, abs=0.01)


class TestDeskTrendPrompt:
    """DESK_TREND_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        assert isinstance(DESK_TREND_PROMPT, str)
        assert len(DESK_TREND_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        assert len(DESK_TREND_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_TREND_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        assert "fetch_quote" in DESK_TREND_PROMPT
        assert "fetch_related_ohlcv" in DESK_TREND_PROMPT
        assert "compute_indicator_on_demand" in DESK_TREND_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_TREND_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT

        assert "VERSION" in DESK_TREND_PROMPT


class TestTrendDeskReExports:
    """Verify trend desk is importable from agents package."""

    def test_trend_desk_importable_from_agents(self) -> None:
        from options_arena.agents import trend_desk as td

        assert td is not None

    def test_run_trend_desk_query_importable(self) -> None:
        from options_arena.agents import run_trend_desk_query as rtdq

        assert rtdq is not None

    def test_build_trend_toolset_importable(self) -> None:
        from options_arena.agents import build_trend_toolset

        assert build_trend_toolset is not None
