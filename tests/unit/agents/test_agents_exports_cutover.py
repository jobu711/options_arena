"""Tests for agents/__init__.py cutover — recommendation exports replace debate exports.

Verifies that:
- Recommendation system exports are present and importable.
- Debate agent instance names are removed from ``__all__``.
- ``run_debate`` is fully removed (not even backward-compat).
- Desk agent and synthesis agent exports remain intact.
- ``DebatePhase`` and ``effective_batch_ticker_delay`` moved to ``_context.py``.

Updated for issue #669 — debate files deleted, backward-compat shims removed.
"""

from __future__ import annotations

import importlib

import pytest

# ---------------------------------------------------------------------------
# Debate agent instances REMOVED from __all__
# ---------------------------------------------------------------------------
_REMOVED_DEBATE_AGENTS = [
    "trend_agent",
    "volatility_agent",
    "flow_agent",
    "fundamental_agent",
    "risk_agent",
    "contrarian_agent",
]


class TestRecommendationExports:
    """Primary recommendation exports are importable and in __all__."""

    def test_run_recommendation_exported(self) -> None:
        """run_recommendation is importable from agents and in __all__."""
        from options_arena.agents import run_recommendation

        assert callable(run_recommendation)

    def test_run_recommendation_in_all(self) -> None:
        """run_recommendation is in __all__."""
        import options_arena.agents as agents_mod

        assert "run_recommendation" in agents_mod.__all__

    def test_recommendation_progress_callback_exported(self) -> None:
        """RecommendationProgressCallback is importable from agents."""
        from options_arena.agents import RecommendationProgressCallback

        assert RecommendationProgressCallback is not None

    def test_should_recommend_exported(self) -> None:
        """should_recommend is importable from agents and in __all__."""
        from options_arena.agents import should_recommend

        assert callable(should_recommend)

    def test_should_recommend_in_all(self) -> None:
        """should_recommend is in __all__."""
        import options_arena.agents as agents_mod

        assert "should_recommend" in agents_mod.__all__


class TestDebateAgentsRemoved:
    """Debate agent instance names are NOT in __all__."""

    @pytest.mark.parametrize("name", _REMOVED_DEBATE_AGENTS)
    def test_debate_agent_not_in_all(self, name: str) -> None:
        """Debate agent instance '{name}' is not in __all__."""
        import options_arena.agents as agents_mod

        assert name not in agents_mod.__all__

    def test_run_debate_not_in_all(self) -> None:
        """run_debate is not in __all__."""
        import options_arena.agents as agents_mod

        assert "run_debate" not in agents_mod.__all__

    def test_debate_deps_not_in_all(self) -> None:
        """DebateDeps is not in __all__."""
        import options_arena.agents as agents_mod

        assert "DebateDeps" not in agents_mod.__all__

    def test_should_debate_not_in_all(self) -> None:
        """should_debate is not in __all__ (replaced by should_recommend)."""
        import options_arena.agents as agents_mod

        assert "should_debate" not in agents_mod.__all__

    def test_synthesize_verdict_not_in_all(self) -> None:
        """synthesize_verdict is not in __all__."""
        import options_arena.agents as agents_mod

        assert "synthesize_verdict" not in agents_mod.__all__

    def test_compute_agreement_score_not_in_all(self) -> None:
        """compute_agreement_score is not in __all__."""
        import options_arena.agents as agents_mod

        assert "compute_agreement_score" not in agents_mod.__all__


class TestMovedSymbolsAccessibleViaContext:
    """Symbols moved from orchestrator.py to _context.py are still importable."""

    def test_debate_phase_importable_from_context(self) -> None:
        """DebatePhase moved to _context.py for backward-compat WS bridges."""
        from options_arena.agents._context import DebatePhase

        assert DebatePhase.TREND == "trend"

    def test_effective_batch_ticker_delay_importable_from_context(self) -> None:
        """effective_batch_ticker_delay moved to _context.py."""
        from options_arena.agents._context import effective_batch_ticker_delay

        assert callable(effective_batch_ticker_delay)


class TestDeskAgentsPreserved:
    """All 7 desk agent exports remain in __all__ and importable."""

    def test_volatility_desk_exported(self) -> None:
        from options_arena.agents import run_vol_desk_query, vol_desk

        assert vol_desk is not None
        assert callable(run_vol_desk_query)

    def test_risk_desk_exported(self) -> None:
        from options_arena.agents import risk_desk, run_risk_desk_query

        assert risk_desk is not None
        assert callable(run_risk_desk_query)

    def test_trend_desk_exported(self) -> None:
        from options_arena.agents import run_trend_desk_query, trend_desk

        assert trend_desk is not None
        assert callable(run_trend_desk_query)

    def test_flow_desk_exported(self) -> None:
        from options_arena.agents import flow_desk, run_flow_desk_query

        assert flow_desk is not None
        assert callable(run_flow_desk_query)

    def test_fundamental_desk_exported(self) -> None:
        from options_arena.agents import fundamental_desk, run_fundamental_desk_query

        assert fundamental_desk is not None
        assert callable(run_fundamental_desk_query)

    def test_contrarian_desk_exported(self) -> None:
        from options_arena.agents import contrarian_desk, run_contrarian_desk_query

        assert contrarian_desk is not None
        assert callable(run_contrarian_desk_query)

    def test_research_desk_exported(self) -> None:
        from options_arena.agents import research_desk, run_research_desk_query

        assert research_desk is not None
        assert callable(run_research_desk_query)

    def test_desk_deps_exported(self) -> None:
        from options_arena.agents import DeskDeps

        assert DeskDeps is not None

    @pytest.mark.parametrize(
        "name",
        [
            "contrarian_desk",
            "flow_desk",
            "fundamental_desk",
            "research_desk",
            "risk_desk",
            "trend_desk",
            "vol_desk",
        ],
    )
    def test_desk_agent_in_all(self, name: str) -> None:
        """Desk agent '{name}' is in __all__."""
        import options_arena.agents as agents_mod

        assert name in agents_mod.__all__


class TestSynthesisExports:
    """Synthesis agent exports present and in __all__."""

    def test_synthesis_agent_exported(self) -> None:
        from options_arena.agents import synthesis_agent

        assert synthesis_agent is not None

    def test_run_synthesis_exported(self) -> None:
        from options_arena.agents import run_synthesis

        assert callable(run_synthesis)

    def test_synthesis_deps_exported(self) -> None:
        from options_arena.agents import SynthesisDeps

        assert SynthesisDeps is not None

    @pytest.mark.parametrize(
        "name",
        ["synthesis_agent", "run_synthesis", "SynthesisDeps"],
    )
    def test_synthesis_in_all(self, name: str) -> None:
        """Synthesis export '{name}' is in __all__."""
        import options_arena.agents as agents_mod

        assert name in agents_mod.__all__


class TestAllCompleteness:
    """Every name in __all__ is actually importable from the package."""

    def test_all_names_importable(self) -> None:
        """Every name listed in __all__ resolves to a real attribute."""
        agents_mod = importlib.import_module("options_arena.agents")
        missing: list[str] = []
        for name in agents_mod.__all__:
            if not hasattr(agents_mod, name):
                missing.append(name)
        assert missing == [], f"Names in __all__ but not importable: {missing}"

    def test_no_duplicates_in_all(self) -> None:
        """__all__ contains no duplicate entries."""
        import options_arena.agents as agents_mod

        all_list = agents_mod.__all__
        assert len(all_list) == len(set(all_list)), "Duplicate entries in __all__"


class TestSharedUtilitiesPreserved:
    """Shared utilities used by both systems remain exported."""

    def test_build_market_context_in_all(self) -> None:
        import options_arena.agents as agents_mod

        assert "build_market_context" in agents_mod.__all__

    def test_extract_agent_predictions_in_all(self) -> None:
        import options_arena.agents as agents_mod

        assert "extract_agent_predictions" in agents_mod.__all__

    def test_classify_macd_signal_in_all(self) -> None:
        import options_arena.agents as agents_mod

        assert "classify_macd_signal" in agents_mod.__all__

    def test_build_debate_model_in_all(self) -> None:
        import options_arena.agents as agents_mod

        assert "build_debate_model" in agents_mod.__all__

    def test_render_context_block_in_all(self) -> None:
        import options_arena.agents as agents_mod

        assert "render_context_block" in agents_mod.__all__
