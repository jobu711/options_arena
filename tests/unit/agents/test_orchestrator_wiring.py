"""Tests for orchestrator wiring — partitioned context and vote weights.

Verifies:
  - 'risk' weight removed from AGENT_VOTE_WEIGHTS (dead code cleanup)
  - Phase 1 agents receive domain-specific context strings
  - Risk (Phase 2) and Contrarian (Phase 3) receive full context
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    run_debate,
)
from options_arena.agents.risk import risk_agent_v2
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    DebateConfig,
    OptionContract,
    Quote,
    TickerInfo,
    TickerScore,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


class TestOrchestratorWiring:
    """Verify orchestrator wiring of partitioned context and vote weights."""

    def test_risk_weight_removed(self) -> None:
        """Verify 'risk' not in AGENT_VOTE_WEIGHTS."""
        assert "risk" not in AGENT_VOTE_WEIGHTS

    def test_expected_weights_present(self) -> None:
        """Verify all expected agent weights are still present."""
        expected = {"trend", "volatility", "flow", "fundamental", "contrarian"}
        assert set(AGENT_VOTE_WEIGHTS.keys()) == expected

    @pytest.mark.asyncio
    async def test_phase1_agents_receive_domain_context(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Phase 1 agents receive domain-specific context, not full context.

        Verifies structural markers:
        - Trend agent sees '## Trend Indicators' but NOT 'COMPOSITE SCORE'
        - Volatility agent sees '## Volatility Indicators' but NOT 'COMPOSITE SCORE'
        - Flow agent sees '## Flow Indicators' but NOT 'COMPOSITE SCORE'
        - Risk and Contrarian see 'COMPOSITE SCORE' (full context)
        """
        captured_prompts: dict[str, str] = {}

        # Capture the prompt string passed to each agent's .run() call
        original_trend_run = trend_agent.run
        original_vol_run = volatility_agent.run
        original_flow_run = flow_agent.run
        original_fund_run = fundamental_agent.run
        original_risk_run = risk_agent_v2.run
        original_contrarian_run = contrarian_agent.run

        async def capture_trend(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["trend"] = str(args[0])
            return await original_trend_run(*args, **kwargs)  # type: ignore[arg-type]

        async def capture_vol(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["volatility"] = str(args[0])
            return await original_vol_run(*args, **kwargs)  # type: ignore[arg-type]

        async def capture_flow(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["flow"] = str(args[0])
            return await original_flow_run(*args, **kwargs)  # type: ignore[arg-type]

        async def capture_fund(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["fundamental"] = str(args[0])
            return await original_fund_run(*args, **kwargs)  # type: ignore[arg-type]

        async def capture_risk(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["risk"] = str(args[0])
            return await original_risk_run(*args, **kwargs)  # type: ignore[arg-type]

        async def capture_contrarian(*args: object, **kwargs: object) -> object:
            if args:
                captured_prompts["contrarian"] = str(args[0])
            return await original_contrarian_run(*args, **kwargs)  # type: ignore[arg-type]

        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            flow_agent.override(model=TestModel()),
            fundamental_agent.override(model=TestModel()),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
            patch.object(trend_agent, "run", side_effect=capture_trend),
            patch.object(volatility_agent, "run", side_effect=capture_vol),
            patch.object(flow_agent, "run", side_effect=capture_flow),
            patch.object(fundamental_agent, "run", side_effect=capture_fund),
            patch.object(risk_agent_v2, "run", side_effect=capture_risk),
            patch.object(contrarian_agent, "run", side_effect=capture_contrarian),
        ):
            await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )

        # All agents should have been called
        assert "trend" in captured_prompts
        assert "volatility" in captured_prompts
        assert "flow" in captured_prompts
        assert "fundamental" in captured_prompts
        assert "risk" in captured_prompts
        assert "contrarian" in captured_prompts

        # Phase 1: domain-specific section headers present
        assert "## Trend Indicators" in captured_prompts["trend"], (
            "Trend agent should see trend-specific section"
        )
        assert "## Volatility Indicators" in captured_prompts["volatility"], (
            "Volatility agent should see volatility-specific section"
        )
        assert "## Flow Indicators" in captured_prompts["flow"], (
            "Flow agent should see flow-specific section"
        )

        # Phase 1: COMPOSITE SCORE excluded from domain contexts
        assert "COMPOSITE SCORE" not in captured_prompts["trend"], (
            "Trend agent should NOT see COMPOSITE SCORE"
        )
        assert "COMPOSITE SCORE" not in captured_prompts["volatility"], (
            "Volatility agent should NOT see COMPOSITE SCORE"
        )
        assert "COMPOSITE SCORE" not in captured_prompts["flow"], (
            "Flow agent should NOT see COMPOSITE SCORE"
        )
        assert "COMPOSITE SCORE" not in captured_prompts["fundamental"], (
            "Fundamental agent should NOT see COMPOSITE SCORE"
        )

        # Phase 1: DIRECTION excluded from domain contexts
        # (check for the exact pattern "DIRECTION: " to avoid matching section headers)
        for agent_name in ("trend", "volatility", "flow", "fundamental"):
            assert "\nDIRECTION: " not in captured_prompts[agent_name], (
                f"{agent_name} agent should NOT see DIRECTION signal"
            )

        # Phase 2 + 3: full context markers present
        assert "COMPOSITE SCORE" in captured_prompts["risk"], (
            "Risk agent should see COMPOSITE SCORE (full context)"
        )
        assert "COMPOSITE SCORE" in captured_prompts["contrarian"], (
            "Contrarian agent should see COMPOSITE SCORE (full context)"
        )
