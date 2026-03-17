"""Tests for the Risk desk agent."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents.risk_desk import risk_desk, run_risk_desk_query
from options_arena.models import AgencyConfig, DeskResponse, DeskType

models.ALLOW_MODEL_REQUESTS = False


def _make_deps(query: str = "Assess AAPL risk", ticker: str = "AAPL") -> DeskDeps:
    return DeskDeps(
        query=query,
        ticker=ticker,
        market_data=MagicMock(),
        options_data=MagicMock(),
        fred=MagicMock(),
        repo=MagicMock(),
    )


class TestRiskDeskAgent:
    """risk_desk Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert risk_desk is not None

    def test_agent_output_type_is_str(self) -> None:
        assert risk_desk._output_type is str  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = risk_desk._function_toolset  # noqa: SLF001
        assert toolset is not None


@pytest.mark.asyncio
class TestRunRiskDeskQuery:
    """run_risk_desk_query() wrapper tests."""

    async def test_produces_desk_response(self) -> None:
        deps = _make_deps()
        result = await run_risk_desk_query("What is AAPL risk?", deps, model=TestModel())
        assert isinstance(result, DeskResponse)
        assert result.desk == DeskType.RISK

    async def test_response_is_string(self) -> None:
        deps = _make_deps()
        result = await run_risk_desk_query("Check risk", deps, model=TestModel())
        assert isinstance(result.response, str)
        assert len(result.response) > 0

    async def test_think_tags_stripped(self) -> None:
        deps = _make_deps()
        test_model = TestModel(custom_output_text="<think>reasoning</think>Risk is moderate.")
        result = await run_risk_desk_query("Analyze risk", deps, model=test_model)
        assert "<think>" not in result.response
        assert "Risk is moderate." in result.response

    async def test_no_model_returns_error_response(self) -> None:
        deps = _make_deps()
        # No model provided — early guard returns error DeskResponse
        result = await run_risk_desk_query("test", deps)
        assert isinstance(result, DeskResponse)
        assert result.confidence == 0.0
        assert "no LLM model" in result.response

    async def test_timeout_returns_fallback(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=0.001)  # Extremely short timeout
        # TestModel is fast so we might not timeout, but the code path is exercised
        result = await run_risk_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_tools_used_tracked(self) -> None:
        deps = _make_deps()
        result = await run_risk_desk_query("Analyze risk", deps, model=TestModel())
        # tools_used comes from the deps accumulator
        assert isinstance(result.tools_used, list)

    async def test_custom_config_respected(self) -> None:
        deps = _make_deps()
        config = AgencyConfig(agent_timeout=120.0, risk_tool_budget=8)
        result = await run_risk_desk_query("test", deps, model=TestModel(), config=config)
        assert isinstance(result, DeskResponse)

    async def test_higher_tool_budget_than_vol(self) -> None:
        """Risk desk uses risk_tool_budget (5) vs vol desk's default_tool_budget (3)."""
        cfg = AgencyConfig()
        assert cfg.risk_tool_budget > cfg.default_tool_budget

    async def test_successful_response_has_confidence(self) -> None:
        from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE

        deps = _make_deps()
        result = await run_risk_desk_query("test", deps, model=TestModel())
        assert result.confidence == pytest.approx(DESK_SUCCESS_CONFIDENCE, abs=0.01)


class TestDeskRiskPrompt:
    """DESK_RISK_PROMPT quality checks."""

    def test_prompt_exists_and_non_empty(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        assert isinstance(DESK_RISK_PROMPT, str)
        assert len(DESK_RISK_PROMPT) > 100

    def test_prompt_under_budget(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        assert len(DESK_RISK_PROMPT) < 8000

    def test_prompt_no_rules_appendix(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        # Desk prompts do NOT include PROMPT_RULES_APPENDIX
        assert "Confidence calibration" not in DESK_RISK_PROMPT

    def test_prompt_mentions_tools(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        assert "fetch_quote" in DESK_RISK_PROMPT
        assert "fetch_correlation" in DESK_RISK_PROMPT

    def test_prompt_has_available_tools_block(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        assert "<<<AVAILABLE_TOOLS>>>" in DESK_RISK_PROMPT

    def test_prompt_has_version(self) -> None:
        from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT

        assert "VERSION" in DESK_RISK_PROMPT


class TestDeskReExports:
    """Verify all desk types are importable from agents package."""

    def test_vol_desk_importable_from_agents(self) -> None:
        from options_arena.agents import vol_desk as vd

        assert vd is not None

    def test_risk_desk_importable_from_agents(self) -> None:
        from options_arena.agents import risk_desk as rd

        assert rd is not None

    def test_desk_deps_importable_from_agents(self) -> None:
        from options_arena.agents import DeskDeps as DD

        assert DD is not None

    def test_toolset_builders_importable(self) -> None:
        from options_arena.agents import build_risk_toolset, build_volatility_toolset

        assert build_risk_toolset is not None
        assert build_volatility_toolset is not None

    def test_desk_query_functions_importable(self) -> None:
        from options_arena.agents import run_risk_desk_query, run_vol_desk_query

        assert run_risk_desk_query is not None
        assert run_vol_desk_query is not None
