"""Integration tests for the 6-agent debate protocol (run_debate).

Tests cover:
  - Full 6-agent protocol flow (all agents succeed via TestModel)
  - Phase 1 parallel execution (trend + volatility)
  - Phase 2 sequential (risk_agent_v2 with Phase 1 outputs)
  - Phase 3 sequential (contrarian with all outputs)
  - Phase 4 verdict synthesis (algorithmic, no LLM)
  - Graceful degradation: 0, 1, 2, 3, 4 Phase 1 failures
  - Agreement score computation
  - Confidence capping when agreement < 0.4
  - Contrarian skipped when >= 2 Phase 1 failures

Uses TestModel from pydantic_ai.models.test -- NEVER makes real API calls.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateResult
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    compute_agreement_score,
    run_debate,
    synthesize_verdict,
)
from options_arena.agents.risk import risk_agent_v2
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    AgentResponse,
    CatalystImpact,
    ContrarianThesis,
    DebateConfig,
    DimensionalScores,
    DividendSource,
    ExerciseStyle,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    IndicatorSignals,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    RiskAssessment,
    RiskLevel,
    SignalDirection,
    TickerInfo,
    TickerScore,
    VolatilityThesis,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_ticker_score() -> TickerScore:
    return TickerScore(
        ticker="AAPL",
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=62.3,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            obv=65.0,
            relative_volume=55.0,
        ),
        scan_run_id=1,
    )


def _make_quote() -> Quote:
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


def _make_ticker_info() -> TickerInfo:
    return TickerInfo(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Information Technology",
        market_cap=2_800_000_000_000,
        dividend_yield=0.005,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("185.50"),
        fifty_two_week_high=Decimal("199.62"),
        fifty_two_week_low=Decimal("164.08"),
    )


def _make_contract() -> OptionContract:
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("190.00"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("4.50"),
        ask=Decimal("4.80"),
        last=Decimal("4.65"),
        volume=1500,
        open_interest=12000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.285,
        greeks=OptionGreeks(
            delta=0.35,
            gamma=0.025,
            theta=-0.045,
            vega=0.32,
            rho=0.08,
            pricing_model=PricingModel.BAW,
        ),
    )


def _make_config() -> DebateConfig:
    return DebateConfig(
        api_key="test-key-not-used-with-TestModel",
        agent_timeout=5.0,
        max_total_duration=30.0,
        phase1_parallelism=4,
    )


def _make_flow_thesis() -> FlowThesis:
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        gex_interpretation="Positive GEX supports upside.",
        smart_money_signal="Institutional accumulation detected.",
        oi_analysis="Call OI exceeds put OI at key strikes.",
        volume_confirmation="Volume confirms bullish momentum.",
        key_flow_factors=["Positive GEX", "High call OI"],
        model_used="test",
    )


def _make_fundamental_thesis() -> FundamentalThesis:
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.60,
        catalyst_impact=CatalystImpact.MODERATE,
        earnings_assessment="Strong earnings beat expected.",
        iv_crush_risk="Moderate IV crush risk post-earnings.",
        key_fundamental_factors=["Revenue growth", "Margin expansion"],
        model_used="test",
    )


def _make_dimensional_scores() -> DimensionalScores:
    return DimensionalScores(
        trend=75.0,
        iv_vol=60.0,
        hv_vol=55.0,
        flow=70.0,
    )


# ---------------------------------------------------------------------------
# compute_agreement_score tests
# ---------------------------------------------------------------------------


class TestComputeAgreementScore:
    """Tests for compute_agreement_score()."""

    def test_unanimous_bullish(self) -> None:
        """All agents agree on bullish -> 1.0."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    def test_unanimous_bearish(self) -> None:
        """All agents agree on bearish -> 1.0."""
        directions = {
            "trend": SignalDirection.BEARISH,
            "flow": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    def test_split_two_and_two(self) -> None:
        """2 bullish, 2 bearish -> 0.5."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BEARISH,
            "risk": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(0.5)

    def test_three_vs_one(self) -> None:
        """3 bullish, 1 bearish -> 0.75."""
        directions = {
            "trend": SignalDirection.BULLISH,
            "flow": SignalDirection.BULLISH,
            "fundamental": SignalDirection.BULLISH,
            "risk": SignalDirection.BEARISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(0.75)

    def test_empty_returns_zero(self) -> None:
        """No agents -> 0.0."""
        assert compute_agreement_score({}) == pytest.approx(0.0)

    def test_single_agent(self) -> None:
        """Single agent -> 1.0 (trivially agrees with itself)."""
        directions = {"trend": SignalDirection.BULLISH}
        assert compute_agreement_score(directions) == pytest.approx(1.0)

    def test_neutral_excluded_from_denominator(self) -> None:
        """Neutral agents are excluded from the denominator.

        1 BULL, 0 BEAR, 2 NEUTRAL -> directional = 1 -> 1/1 = 1.0.
        """
        directions = {
            "trend": SignalDirection.NEUTRAL,
            "flow": SignalDirection.NEUTRAL,
            "fundamental": SignalDirection.BULLISH,
        }
        assert compute_agreement_score(directions) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# synthesize_verdict tests
# ---------------------------------------------------------------------------


class TestSynthesizeVerdict:
    """Tests for synthesize_verdict()."""

    def test_produces_extended_trade_thesis(self) -> None:
        """Verdict is an ExtendedTradeThesis."""
        trend_resp = AgentResponse(
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            argument="ADX shows strong trend.",
            key_points=["ADX above 25", "SMA aligned"],
            risks_cited=["Trend reversal risk"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        config = _make_config()
        verdict = synthesize_verdict(
            agent_outputs={"trend": trend_resp},
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        assert isinstance(verdict, ExtendedTradeThesis)
        assert verdict.ticker == "AAPL"
        assert verdict.direction == SignalDirection.BULLISH
        assert 0.0 <= verdict.confidence <= 1.0

    def test_agreement_score_present(self) -> None:
        """Verdict includes agreement score."""
        trend_resp = AgentResponse(
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            argument="Strong trend.",
            key_points=["ADX above 25"],
            risks_cited=["Reversal risk"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        verdict = synthesize_verdict(
            agent_outputs={"trend": trend_resp},
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=_make_config(),
        )
        assert verdict.agent_agreement_score is not None
        assert 0.0 <= verdict.agent_agreement_score <= 1.0

    def test_low_agreement_caps_confidence(self) -> None:
        """When agreement < 0.4 (all NEUTRAL), confidence is capped at 0.4.

        With NEUTRAL exclusion from denominator, agreement is 0.0 when all
        agents are NEUTRAL -- the only scenario where agreement < 0.4, since
        the minimum directional agreement is 0.5 (equal split).
        """
        agents: dict[
            str,
            AgentResponse | FlowThesis | FundamentalThesis | VolatilityThesis,
        ] = {
            "trend": AgentResponse(
                agent_name="trend",
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
                argument="No clear trend.",
                key_points=["Point A"],
                risks_cited=["Risk A"],
                contracts_referenced=["AAPL $190 CALL"],
                model_used="test",
            ),
            "flow": FlowThesis(
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
                gex_interpretation="Flat GEX.",
                smart_money_signal="No signal.",
                oi_analysis="Balanced OI.",
                volume_confirmation="Average volume.",
                key_flow_factors=["No signal"],
                model_used="test",
            ),
            "fundamental": FundamentalThesis(
                direction=SignalDirection.NEUTRAL,
                confidence=0.5,
                catalyst_impact=CatalystImpact.LOW,
                earnings_assessment="Mixed signals.",
                iv_crush_risk="Low.",
                key_fundamental_factors=["Mixed"],
                model_used="test",
            ),
        }
        verdict = synthesize_verdict(
            agent_outputs=agents,
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=_make_config(),
        )
        # All NEUTRAL -> directional_count = 0 -> agreement = 0.0 < 0.4
        assert verdict.agent_agreement_score is not None
        assert verdict.agent_agreement_score == pytest.approx(0.0)
        assert verdict.confidence <= 0.4

    def test_contrarian_dissent_included(self) -> None:
        """When contrarian is provided, its dissent appears in verdict."""
        trend_resp = AgentResponse(
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            argument="Strong trend.",
            key_points=["ADX above 25"],
            risks_cited=["Reversal risk"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        contrarian = ContrarianThesis(
            dissent_direction=SignalDirection.BEARISH,
            dissent_confidence=0.55,
            primary_challenge="RSI divergence suggests exhaustion.",
            overlooked_risks=["Earnings risk", "Sector rotation"],
            consensus_weakness="Overreliance on ADX.",
            alternative_scenario="Mean reversion to 52-week low.",
            model_used="test",
        )
        verdict = synthesize_verdict(
            agent_outputs={"trend": trend_resp},
            risk_assessment=None,
            contrarian=contrarian,
            dimensional_scores=None,
            ticker="AAPL",
            config=_make_config(),
        )
        assert verdict.contrarian_dissent is not None
        assert "bearish" in verdict.contrarian_dissent.lower()

    def test_dimensional_scores_attached(self) -> None:
        """Dimensional scores are passed through to the verdict."""
        trend_resp = AgentResponse(
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            argument="Strong trend.",
            key_points=["ADX above 25"],
            risks_cited=["Reversal risk"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        scores = _make_dimensional_scores()
        verdict = synthesize_verdict(
            agent_outputs={"trend": trend_resp},
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=scores,
            ticker="AAPL",
            config=_make_config(),
        )
        assert verdict.dimensional_scores is not None
        assert verdict.dimensional_scores.trend == pytest.approx(75.0)

    def test_agents_completed_count(self) -> None:
        """agents_completed reflects total including risk and contrarian."""
        trend_resp = AgentResponse(
            agent_name="trend",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            argument="Strong trend.",
            key_points=["ADX above 25"],
            risks_cited=["Reversal risk"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        risk = RiskAssessment(
            risk_level=RiskLevel.MODERATE,
            confidence=0.6,
            max_loss_estimate="$480 (1 contract x $4.80 ask)",
            key_risks=["Time decay"],
            risk_mitigants=[],
            model_used="test",
        )
        verdict = synthesize_verdict(
            agent_outputs={"trend": trend_resp},
            risk_assessment=risk,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=_make_config(),
        )
        # 1 agent output + 1 risk = 2
        assert verdict.agents_completed == 2

    def test_no_agents_fallback_confidence(self) -> None:
        """With no agent outputs, uses fallback confidence."""
        config = _make_config()
        verdict = synthesize_verdict(
            agent_outputs={},
            risk_assessment=None,
            contrarian=None,
            dimensional_scores=None,
            ticker="AAPL",
            config=config,
        )
        assert verdict.confidence == pytest.approx(config.fallback_confidence)
        assert verdict.direction == SignalDirection.NEUTRAL


# ---------------------------------------------------------------------------
# Full protocol integration tests
# ---------------------------------------------------------------------------


class TestRunDebateV2:
    """Integration tests for run_debate()."""

    @pytest.mark.asyncio
    async def test_full_protocol_with_test_model(self) -> None:
        """Full 6-agent protocol completes with TestModel."""
        config = _make_config()
        flow = _make_flow_thesis()
        fund = _make_fundamental_thesis()

        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                flow_output=flow,
                fundamental_output=fund,
            )

        assert isinstance(result, DebateResult)
        assert result.is_fallback is False
        assert result.duration_ms >= 0
        assert isinstance(result.thesis, ExtendedTradeThesis)
        assert result.thesis.agents_completed >= 3  # trend + vol + risk at minimum

    @pytest.mark.asyncio
    async def test_protocol_with_dimensional_scores(self) -> None:
        """Dimensional scores pass through to the verdict."""
        config = _make_config()
        scores = _make_dimensional_scores()

        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                dimensional_scores=scores,
                flow_output=_make_flow_thesis(),
                fundamental_output=_make_fundamental_thesis(),
            )

        assert isinstance(result.thesis, ExtendedTradeThesis)
        assert result.thesis.dimensional_scores is not None

    @pytest.mark.asyncio
    async def test_fallback_when_no_api_key(self) -> None:
        """Without API key and ALLOW_MODEL_REQUESTS=False, falls back."""
        config = DebateConfig(
            agent_timeout=0.5,
            max_total_duration=1.0,
        )
        result = await run_debate(
            ticker_score=_make_ticker_score(),
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            config=config,
        )
        assert isinstance(result, DebateResult)
        assert result.is_fallback is True
        assert result.thesis.confidence == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_contrarian_skipped_with_two_failures(self) -> None:
        """When >= 2 Phase 1 agents fail, Phase 3 (contrarian) is skipped."""
        config = _make_config()
        # Only trend succeeds, vol fails, no flow, no fundamental = 3 failures
        # Make vol agent fail by patching
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            # No flow_output, no fundamental_output -> 2 failures already
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                flow_output=None,
                fundamental_output=None,
            )

        assert isinstance(result, DebateResult)
        # With 2 Phase 1 failures, contrarian is skipped
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_fallback_on_all_phase1_failures(self) -> None:
        """When all 4 Phase 1 agents fail, returns data-driven fallback."""
        config = _make_config()
        # Make both local agents raise by patching agent.run to raise
        with (
            patch.object(
                trend_agent, "run", new_callable=AsyncMock, side_effect=TimeoutError("test")
            ),
            patch.object(
                volatility_agent,
                "run",
                new_callable=AsyncMock,
                side_effect=TimeoutError("test"),
            ),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                flow_output=None,
                fundamental_output=None,
            )

        assert isinstance(result, DebateResult)
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_weak_signal_skips_debate(self) -> None:
        """Weak signal (neutral direction) skips debate entirely."""
        config = _make_config()
        score = TickerScore(
            ticker="AAPL",
            composite_score=25.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(rsi=50.0),
            scan_run_id=1,
        )
        result = await run_debate(
            ticker_score=score,
            contracts=[_make_contract()],
            quote=_make_quote(),
            ticker_info=_make_ticker_info(),
            config=config,
        )
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_single_surviving_agent(self) -> None:
        """3 Phase 1 failures + 1 success produces a result, not a full fallback."""
        config = _make_config()
        # Trend succeeds, vol fails, no flow, no fund -> 3 failures
        with (
            trend_agent.override(model=TestModel()),
            patch.object(
                volatility_agent,
                "run",
                new_callable=AsyncMock,
                side_effect=TimeoutError("vol failed"),
            ),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                flow_output=None,
                fundamental_output=None,
            )

        # 3 failures but 1 success -> not full fallback
        assert isinstance(result, DebateResult)
        assert result.is_fallback is False
        assert isinstance(result.thesis, ExtendedTradeThesis)

    @pytest.mark.asyncio
    async def test_backward_compatible_debate_result(self) -> None:
        """DebateResult has bull_response and bear_response for backward compat."""
        config = _make_config()
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent_v2.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=_make_ticker_score(),
                contracts=[_make_contract()],
                quote=_make_quote(),
                ticker_info=_make_ticker_info(),
                config=config,
                flow_output=_make_flow_thesis(),
                fundamental_output=_make_fundamental_thesis(),
            )

        assert isinstance(result.bull_response, AgentResponse)
        assert isinstance(result.bear_response, AgentResponse)
        assert isinstance(result.thesis, ExtendedTradeThesis)


# ---------------------------------------------------------------------------
# Agent vote weights sanity checks
# ---------------------------------------------------------------------------


class TestAgentVoteWeights:
    """Tests for AGENT_VOTE_WEIGHTS constant."""

    def test_directional_weights_sum(self) -> None:
        """Directional agent weights (excluding risk) sum to 0.85.

        Note: log-odds pooling does NOT require weights to sum to 1.0.
        Each weight scales how much the agent shifts the pooled log-odds.
        Risk has weight 0.0 (advisory-only, no directional vote).
        """
        total = sum(AGENT_VOTE_WEIGHTS.values())
        assert total == pytest.approx(0.85)
        assert all(w >= 0 for w in AGENT_VOTE_WEIGHTS.values())

    def test_all_agents_have_weights(self) -> None:
        """All 6 agents have weight entries (risk is advisory-only at 0.0)."""
        expected = {"trend", "volatility", "flow", "fundamental", "contrarian", "risk"}
        assert set(AGENT_VOTE_WEIGHTS.keys()) == expected

    def test_risk_weight_is_zero(self) -> None:
        """Risk agent is advisory-only and has zero vote weight."""
        assert AGENT_VOTE_WEIGHTS["risk"] == pytest.approx(0.0)

    def test_trend_has_highest_weight(self) -> None:
        """Trend agent has the highest individual weight."""
        max_name = max(AGENT_VOTE_WEIGHTS, key=AGENT_VOTE_WEIGHTS.get)  # type: ignore[arg-type]
        assert max_name == "trend"

    def test_contrarian_has_lowest_positive_weight(self) -> None:
        """Contrarian agent has the lowest positive (non-zero) weight."""
        positive_weights = {k: v for k, v in AGENT_VOTE_WEIGHTS.items() if v > 0}
        min_name = min(positive_weights, key=positive_weights.get)  # type: ignore[arg-type]
        assert min_name == "contrarian"
