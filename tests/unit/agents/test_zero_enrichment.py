"""Tests for zero-enrichment agent execution (#326).

Verifies that Flow and Fundamental agents run successfully with zero
enrichment data, that the context block includes a data-availability
note, and that compute_agreement_score works with 6 agents.
"""

from __future__ import annotations

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateDeps, render_context_block
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.orchestrator import compute_agreement_score
from options_arena.models import (
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    OptionContract,
    SignalDirection,
    TickerScore,
)

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Flow agent — zero enrichment
# ---------------------------------------------------------------------------


class TestFlowAgentZeroEnrichment:
    """Flow agent produces valid output with zero enrichment data."""

    @pytest.mark.asyncio()
    async def test_flow_agent_valid_output_zero_enrichment(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
    ) -> None:
        """Flow agent produces valid FlowThesis with zero-enrichment MarketContext."""
        assert mock_market_context.enrichment_ratio() == pytest.approx(0.0)
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
        )
        with flow_agent.override(model=TestModel()):
            result = await flow_agent.run(
                f"Analyze options flow for {mock_market_context.ticker}.",
                deps=deps,
                model=TestModel(),
            )
        assert isinstance(result.output, FlowThesis)
        assert 0.0 <= result.output.confidence <= 1.0
        assert result.output.direction in {
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        }


# ---------------------------------------------------------------------------
# Fundamental agent — zero enrichment
# ---------------------------------------------------------------------------


class TestFundamentalAgentZeroEnrichment:
    """Fundamental agent produces valid output with zero enrichment data."""

    @pytest.mark.asyncio()
    async def test_fundamental_agent_valid_output_zero_enrichment(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
    ) -> None:
        """Fundamental agent produces valid FundamentalThesis with zero enrichment."""
        assert mock_market_context.enrichment_ratio() == pytest.approx(0.0)
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
        )
        with fundamental_agent.override(model=TestModel()):
            result = await fundamental_agent.run(
                f"Assess fundamental catalysts for {mock_market_context.ticker}.",
                deps=deps,
                model=TestModel(),
            )
        assert isinstance(result.output, FundamentalThesis)
        assert 0.0 <= result.output.confidence <= 1.0
        assert result.output.direction in {
            SignalDirection.BULLISH,
            SignalDirection.BEARISH,
            SignalDirection.NEUTRAL,
        }


# ---------------------------------------------------------------------------
# Context block — enrichment note
# ---------------------------------------------------------------------------


class TestContextBlockEnrichmentNote:
    """Tests for data-availability note in context block."""

    def test_context_block_note_zero_enrichment(
        self,
        mock_market_context: MarketContext,
    ) -> None:
        """Context block includes data-availability note when enrichment absent."""
        assert mock_market_context.enrichment_ratio() == pytest.approx(0.0)
        text = render_context_block(mock_market_context)
        assert "Enrichment data not available" in text
        assert "scan-derived indicators" in text

    def test_context_block_no_note_with_enrichment(
        self,
        mock_market_context: MarketContext,
    ) -> None:
        """Context block omits note when enrichment data present."""
        # Set some enrichment fields to make enrichment_ratio > 0
        mock_market_context.pe_ratio = 28.5
        mock_market_context.forward_pe = 25.0
        mock_market_context.profit_margin = 0.26
        assert mock_market_context.enrichment_ratio() > 0.0
        text = render_context_block(mock_market_context)
        assert "Enrichment data not available" not in text


# ---------------------------------------------------------------------------
# Agreement score — 6 agents
# ---------------------------------------------------------------------------


class TestAgreementScoreSixAgents:
    """Tests for compute_agreement_score with 6 agents."""

    def test_agreement_score_six_agents_all_agree(self) -> None:
        """Agreement score is 1.0 when all 6 agents agree."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
            "risk": SignalDirection.BULLISH,
            "contrarian": SignalDirection.BULLISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    def test_agreement_score_six_agents_four_two_split(self) -> None:
        """Agreement score reflects 4/6 majority among directional agents."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
            "risk": SignalDirection.BEARISH,
            "contrarian": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(4.0 / 6.0)

    def test_agreement_score_six_agents_flow_fundamental_dissent(self) -> None:
        """Flow + fundamental dissenting yields 4/6 agreement."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
            "risk": SignalDirection.BULLISH,
            "contrarian": SignalDirection.BULLISH,
            "flow": SignalDirection.BEARISH,
            "fundamental": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(4.0 / 6.0)


# ---------------------------------------------------------------------------
# Agreement score — NEUTRAL exclusion (#361)
# ---------------------------------------------------------------------------


class TestAgreementNeutralExclusion:
    """Tests for NEUTRAL exclusion from agreement denominator."""

    def test_all_neutral_returns_zero(self) -> None:
        """All NEUTRAL agents -> agreement = 0.0."""
        directions = {
            "trend": SignalDirection.NEUTRAL,
            "volatility": SignalDirection.NEUTRAL,
            "flow": SignalDirection.NEUTRAL,
        }
        assert compute_agreement_score(directions) == pytest.approx(0.0)

    def test_neutral_excluded_from_denominator(self) -> None:
        """3 BULL + 1 NEUTRAL -> agreement = 3/3 = 1.0, not 3/4 = 0.75."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.NEUTRAL,
        }
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    def test_mixed_with_neutral_higher_agreement(self) -> None:
        """2 BULL + 1 BEAR + 1 NEUTRAL -> agreement = 2/3, not 2/4."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "volatility": SignalDirection.BULLISH,
            "flow": SignalDirection.BEARISH,
            "fundamental": SignalDirection.NEUTRAL,
        }
        assert compute_agreement_score(directions) == pytest.approx(2.0 / 3.0)
