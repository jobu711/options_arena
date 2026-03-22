"""Verify that the 13 deleted debate files are no longer importable.

Issue #669: Delete 13 debate files and clean up _parsing.py.
This test file ensures:
- All 6 debate agent modules raise ImportError
- All 6 debate prompt modules raise ImportError
- The orchestrator module raises ImportError
- The agents package still imports correctly
- Shared utilities (strip_think_tags, PROMPT_RULES_APPENDIX) are preserved
- Desk agents remain unaffected
"""

from __future__ import annotations

import importlib

import pytest


class TestDebateAgentModulesDeleted:
    """Verify the 6 debate agent modules are not importable."""

    @pytest.mark.parametrize(
        "module",
        [
            "options_arena.agents.trend_agent",
            "options_arena.agents.volatility",
            "options_arena.agents.flow_agent",
            "options_arena.agents.fundamental_agent",
            "options_arena.agents.risk",
            "options_arena.agents.contrarian_agent",
        ],
    )
    def test_debate_agent_module_not_importable(self, module: str) -> None:
        """Each deleted debate agent module must raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module(module)


class TestOrchestratorDeleted:
    """Verify the orchestrator module is not importable."""

    def test_orchestrator_not_importable(self) -> None:
        """Deleted orchestrator module must raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("options_arena.agents.orchestrator")


class TestDebatePromptModulesDeleted:
    """Verify the 6 debate prompt modules are not importable."""

    @pytest.mark.parametrize(
        "module",
        [
            "options_arena.agents.prompts.trend_agent",
            "options_arena.agents.prompts.volatility",
            "options_arena.agents.prompts.flow_agent",
            "options_arena.agents.prompts.fundamental_agent",
            "options_arena.agents.prompts.risk",
            "options_arena.agents.prompts.contrarian_agent",
        ],
    )
    def test_debate_prompt_module_not_importable(self, module: str) -> None:
        """Each deleted debate prompt module must raise ImportError."""
        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module(module)


class TestAgentsPackageIntact:
    """Verify the agents package still works after deletion."""

    def test_agents_package_importable(self) -> None:
        """The agents package itself must be importable."""
        import options_arena.agents

        assert hasattr(options_arena.agents, "run_recommendation")

    def test_run_recommendation_importable(self) -> None:
        """Primary entry point must be importable."""
        from options_arena.agents import run_recommendation

        assert callable(run_recommendation)

    def test_should_recommend_importable(self) -> None:
        """Gate function must be importable."""
        from options_arena.agents import should_recommend

        assert callable(should_recommend)


class TestSharedUtilitiesPreserved:
    """Verify shared utilities not accidentally deleted."""

    def test_strip_think_tags_preserved(self) -> None:
        """strip_think_tags must remain in _parsing.py."""
        from options_arena.agents._parsing import strip_think_tags

        assert callable(strip_think_tags)
        assert strip_think_tags("hello") == "hello"
        assert strip_think_tags("<think>reasoning</think>answer") == "answer"

    def test_prompt_rules_appendix_preserved(self) -> None:
        """PROMPT_RULES_APPENDIX must remain in _parsing.py."""
        from options_arena.agents._parsing import PROMPT_RULES_APPENDIX

        assert isinstance(PROMPT_RULES_APPENDIX, str)
        assert len(PROMPT_RULES_APPENDIX) > 100

    def test_build_cleaned_domain_assessment_preserved(self) -> None:
        """build_cleaned_domain_assessment must remain (used by desk agents)."""
        from options_arena.agents._parsing import build_cleaned_domain_assessment

        assert callable(build_cleaned_domain_assessment)

    def test_render_context_block_preserved(self) -> None:
        """render_context_block must remain (used by recommendation orchestrator)."""
        from options_arena.agents._parsing import render_context_block

        assert callable(render_context_block)

    def test_compute_citation_density_preserved(self) -> None:
        """compute_citation_density must remain (used by recommendation orchestrator)."""
        from options_arena.agents._parsing import compute_citation_density

        assert callable(compute_citation_density)

    def test_debate_result_preserved(self) -> None:
        """DebateResult class must remain for backward-compat data parsing."""
        from options_arena.agents._parsing import DebateResult

        assert DebateResult is not None

    def test_debate_deps_removed(self) -> None:
        """DebateDeps must be removed (no remaining consumers)."""
        with pytest.raises(ImportError):
            from options_arena.agents._parsing import (
                DebateDeps,  # type: ignore[attr-defined]  # noqa: F401
            )


class TestDeskAgentsUnaffected:
    """Verify desk agents still importable after debate file deletion."""

    def test_vol_desk_importable(self) -> None:
        from options_arena.agents import run_vol_desk_query

        assert callable(run_vol_desk_query)

    def test_risk_desk_importable(self) -> None:
        from options_arena.agents import run_risk_desk_query

        assert callable(run_risk_desk_query)

    def test_trend_desk_importable(self) -> None:
        from options_arena.agents import run_trend_desk_query

        assert callable(run_trend_desk_query)

    def test_flow_desk_importable(self) -> None:
        from options_arena.agents import run_flow_desk_query

        assert callable(run_flow_desk_query)

    def test_fundamental_desk_importable(self) -> None:
        from options_arena.agents import run_fundamental_desk_query

        assert callable(run_fundamental_desk_query)

    def test_contrarian_desk_importable(self) -> None:
        from options_arena.agents import run_contrarian_desk_query

        assert callable(run_contrarian_desk_query)

    def test_research_desk_importable(self) -> None:
        from options_arena.agents import run_research_desk_query

        assert callable(run_research_desk_query)


class TestMovedSymbolsAccessible:
    """Verify symbols moved from orchestrator.py are still accessible."""

    def test_debate_phase_in_context(self) -> None:
        """DebatePhase moved to _context.py for backward-compat WS bridges."""
        from options_arena.agents._context import DebatePhase

        assert DebatePhase.TREND == "trend"

    def test_effective_batch_ticker_delay_in_context(self) -> None:
        """effective_batch_ticker_delay moved to _context.py."""
        from options_arena.agents._context import effective_batch_ticker_delay

        assert callable(effective_batch_ticker_delay)
