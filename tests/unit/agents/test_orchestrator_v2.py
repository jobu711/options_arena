"""Tests for agent output wiring through orchestrator to persistence.

Tests cover:
  - run_debate populates all 4 agent fields on DebateResult
    (flow, fundamental, risk, contrarian)
  - _persist_result serializes agent fields to save_debate
  - run_debate partial agent failure produces DebateResult with None for failed agent
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateResult
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.orchestrator import run_debate
from options_arena.agents.risk import risk_agent
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    CatalystImpact,
    ContrarianThesis,
    DebateConfig,
    FlowThesis,
    FundamentalThesis,
    OptionContract,
    Quote,
    RiskAssessment,
    RiskLevel,
    SignalDirection,
    TickerInfo,
    TickerScore,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helpers — build model fixtures
# ---------------------------------------------------------------------------


def _make_flow_thesis() -> FlowThesis:
    """Build a realistic FlowThesis for test assertions."""
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        gex_interpretation="Positive GEX suggests dealer hedging supports upside.",
        smart_money_signal="Large block calls detected at the 190 strike.",
        oi_analysis="Open interest skew favors calls 2:1 over puts.",
        volume_confirmation="Volume spike confirms institutional interest.",
        key_flow_factors=["GEX positive", "Call skew 2:1"],
        model_used="test",
    )


def _make_fundamental_thesis() -> FundamentalThesis:
    """Build a realistic FundamentalThesis for test assertions."""
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        catalyst_impact=CatalystImpact.MODERATE,
        earnings_assessment="Earnings beat expected based on recent guidance.",
        iv_crush_risk="Moderate IV crush risk post-earnings.",
        key_fundamental_factors=["Revenue growth 12%", "Forward P/E reasonable"],
        model_used="test",
    )


def _make_risk_assessment() -> RiskAssessment:
    """Build a realistic RiskAssessment for test assertions."""
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.60,
        max_loss_estimate="$480 per contract (premium paid).",
        key_risks=["Earnings event risk", "Broad market correlation"],
        risk_mitigants=["Defined risk via long call", "DTE > 30"],
        model_used="test",
    )


def _make_contrarian_thesis() -> ContrarianThesis:
    """Build a realistic ContrarianThesis for test assertions."""
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.45,
        primary_challenge="Consensus overlooks macro headwinds from rate policy.",
        overlooked_risks=["Fed hawkish pivot", "China export slowdown"],
        consensus_weakness="Over-reliance on momentum indicators ignoring macro.",
        alternative_scenario="Bearish reversal if rates rise above 5%.",
        model_used="test",
    )


# ---------------------------------------------------------------------------
# TestRunDebatePopulates — agent fields on DebateResult
# ---------------------------------------------------------------------------


class TestRunDebatePopulates:
    """run_debate populates agent output fields on DebateResult."""

    @pytest.mark.asyncio
    async def test_debate_populates_all_fields(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """All 4 agent outputs are populated when all agents succeed.

        Provides pre-computed flow_output and fundamental_output to bypass
        the enrichment_ratio gate (no OpenBB data in test fixtures). This
        ensures Phase 1 has < 2 failures so the contrarian agent runs.
        """
        config = DebateConfig(
            api_key="test-key-not-used-with-TestModel",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
                flow_output=_make_flow_thesis(),
                fundamental_output=_make_fundamental_thesis(),
            )
        assert isinstance(result, DebateResult)
        assert result.is_fallback is False
        assert result.flow_response is not None
        assert isinstance(result.flow_response, FlowThesis)
        assert result.fundamental_response is not None
        assert isinstance(result.fundamental_response, FundamentalThesis)
        assert result.risk_response is not None
        assert isinstance(result.risk_response, RiskAssessment)
        assert result.contrarian_response is not None
        assert isinstance(result.contrarian_response, ContrarianThesis)


# ---------------------------------------------------------------------------
# TestPersistResult — serialization to save_debate
# ---------------------------------------------------------------------------


class TestPersistResult:
    """_persist_result serializes agent fields to save_debate."""

    @pytest.mark.asyncio
    async def test_persist_result_serializes(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """save_debate receives model objects when debate is persisted.

        Provides pre-computed flow/fundamental to bypass enrichment gate.
        """
        mock_repo = MagicMock()
        mock_repo.save_debate = AsyncMock(return_value=1)
        mock_repo.get_recommended_contract_id = AsyncMock(return_value=42)
        mock_repo.save_agent_predictions = AsyncMock()

        config = DebateConfig(
            api_key="test-key-not-used-with-TestModel",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
                repository=mock_repo,
                flow_output=_make_flow_thesis(),
                fundamental_output=_make_fundamental_thesis(),
            )

        mock_repo.save_debate.assert_awaited_once()
        call_kwargs = mock_repo.save_debate.call_args.kwargs

        # Agent fields are passed as model objects (not JSON strings)
        assert call_kwargs["flow_thesis"] is not None
        assert isinstance(call_kwargs["flow_thesis"], FlowThesis)
        assert call_kwargs["fundamental_thesis"] is not None
        assert isinstance(call_kwargs["fundamental_thesis"], FundamentalThesis)
        assert call_kwargs["risk_assessment"] is not None
        assert isinstance(call_kwargs["risk_assessment"], RiskAssessment)
        assert call_kwargs["contrarian_thesis"] is not None
        assert isinstance(call_kwargs["contrarian_thesis"], ContrarianThesis)

        # Agent predictions saved with recommended_contract_id populated
        mock_repo.get_recommended_contract_id.assert_awaited_once()
        mock_repo.save_agent_predictions.assert_awaited_once()
        saved_predictions = mock_repo.save_agent_predictions.call_args[0][0]
        assert len(saved_predictions) > 0
        for pred in saved_predictions:
            assert pred.recommended_contract_id == 42


# ---------------------------------------------------------------------------
# TestFallbackOnAgentFailure — partial failure
# ---------------------------------------------------------------------------


class TestFallbackOnAgentFailure:
    """Partial agent failure produces DebateResult with None for failed agents."""

    @pytest.mark.asyncio
    async def test_fallback_on_agent_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """When all Phase 1 agents fail, result is data-driven fallback with agent fields None."""
        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
        )

        async def fake_run_pipeline(*args: object, **kwargs: object) -> None:
            raise RuntimeError("All agents failed")

        monkeypatch.setattr(
            "options_arena.agents.orchestrator._run_debate_pipeline",
            fake_run_pipeline,
        )
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
        )
        assert result.is_fallback is True
        # Fallback results should NOT populate agent fields
        assert result.flow_response is None
        assert result.fundamental_response is None
        assert result.risk_response is None
        assert result.contrarian_response is None
