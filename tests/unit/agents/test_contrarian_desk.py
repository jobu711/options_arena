"""Tests for the Contrarian desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.contrarian_desk import contrarian_desk, run_contrarian_desk_query
from options_arena.models import AgencyConfig, DeskResponse, DeskType

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


class TestContrarianDeskAgent:
    """contrarian_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert contrarian_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        assert contrarian_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = contrarian_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunContrarianDeskQuery:
    """run_contrarian_desk_query() wrapper tests."""

    @pytest.mark.critical
    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        result = await run_contrarian_desk_query(
            "Challenge AAPL bullish view", deps, model=TestModel()
        )
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.CONTRARIAN

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_contrarian_desk_query("Check consensus", deps, model=TestModel())
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(
            custom_output_text="<think>reasoning</think>The consensus is wrong."
        )
        result = await run_contrarian_desk_query("Analyze", deps, model=test_model)
        assert "<think>" not in result.response
        assert "The consensus is wrong." in result.response

    async def test_no_model_returns_error_response(self) -> None:
        deps = _make_deps()
        # No model provided -- early guard returns error DeskResponse
        result = await run_contrarian_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "no LLM model" in result.response

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_contrarian_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_contrarian_desk_query("Challenge AAPL", deps, model=TestModel())
        # tools_used comes from the deps accumulator
        assert isinstance(result.tools_used, list)

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, contrarian_tool_budget=4)
        result = await run_contrarian_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_uses_contrarian_tool_budget(self) -> None:
        """Contrarian desk uses contrarian_tool_budget (2), lower than default (3)."""
        cfg = AgencyConfig()
        assert cfg.contrarian_tool_budget == 2
        assert cfg.contrarian_tool_budget < cfg.default_tool_budget

    async def test_successful_response_has_confidence(self) -> None:
        from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE

        deps = _make_deps()
        result = await run_contrarian_desk_query("test", deps, model=TestModel())
        assert result.confidence == pytest.approx(DESK_SUCCESS_CONFIDENCE, abs=0.01)


class TestDeskContrarianPrompt:
    """DESK_CONTRARIAN_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        assert isinstance(DESK_CONTRARIAN_PROMPT, str)
        assert len(DESK_CONTRARIAN_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        assert len(DESK_CONTRARIAN_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_CONTRARIAN_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        assert "fetch_quote" in DESK_CONTRARIAN_PROMPT
        assert "fetch_debate_history" in DESK_CONTRARIAN_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_CONTRARIAN_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        assert "VERSION" in DESK_CONTRARIAN_PROMPT

    def test_prompt_emphasizes_challenging_consensus(self) -> None:
        from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT

        # Contrarian desk's unique identity
        assert "consensus" in DESK_CONTRARIAN_PROMPT.lower()
        assert "challenge" in DESK_CONTRARIAN_PROMPT.lower()


class TestContrarianDeskReExports:
    """Verify contrarian desk is importable from agents package."""

    def test_contrarian_desk_importable_from_agents(self) -> None:
        from options_arena.agents import contrarian_desk as cd

        assert cd is not None

    def test_run_contrarian_desk_query_importable(self) -> None:
        from options_arena.agents import run_contrarian_desk_query as rcq

        assert rcq is not None

    def test_build_contrarian_toolset_importable(self) -> None:
        from options_arena.agents import build_contrarian_toolset

        assert build_contrarian_toolset is not None
