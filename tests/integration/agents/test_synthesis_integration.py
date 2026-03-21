"""Integration tests for synthesis agent with TestModel."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic_ai import models
from pydantic_ai.usage import RunUsage

from options_arena.models import (
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    OptionContract,
    OptionType,
    SignalDirection,
    TickerScore,
)
from options_arena.models.recommendation import (
    AnyAssessment,
    ContrarianAssessment,
    FlowAssessment,
    FundamentalAssessment,
    PositionRecommendation,
    RecommendationResult,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.models.scan import IndicatorSignals

models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSESSMENT_DEFAULTS: dict[str, object] = {
    "direction": SignalDirection.BULLISH,
    "confidence": 0.70,
    "summary": "Test assessment summary.",
    "key_factors": ["Factor A", "Factor B"],
    "risks": ["Risk 1"],
    "contracts_referenced": ["AAPL 190C 2026-04-18"],
    "tools_used": ["fetch_quote"],
    "model_used": "test-model",
}


def _make_market_context() -> MarketContext:
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("200.00"),
        price_52w_low=Decimal("140.00"),
        iv_rank=45.0,
        iv_percentile=50.0,
        atm_iv_30d=0.28,
        rsi_14=55.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("185.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 3, 1, 14, 30, 0, tzinfo=UTC),
    )


def _make_ticker_score() -> TickerScore:
    return TickerScore(
        ticker="AAPL",
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0, adx=70.0),
    )


def _make_contract() -> OptionContract:
    return OptionContract(
        ticker="AAPL",
        option_type=OptionType.CALL,
        strike=Decimal("185.00"),
        expiration=date.today() + timedelta(days=45),
        bid=Decimal("5.00"),
        ask=Decimal("5.50"),
        last=Decimal("5.25"),
        volume=100,
        open_interest=500,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.30,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSynthesisIntegration:
    """Integration tests for the synthesis agent pipeline."""

    def test_synthesis_agent_importable_from_package(self) -> None:
        """from options_arena.agents import synthesis_agent, run_synthesis, SynthesisDeps works."""
        from options_arena.agents import SynthesisDeps, run_synthesis, synthesis_agent

        assert synthesis_agent is not None
        assert run_synthesis is not None
        assert SynthesisDeps is not None

    @pytest.mark.asyncio
    @pytest.mark.critical
    async def test_full_chain_with_test_model(self) -> None:
        """run_synthesis with model=None triggers fallback and returns PositionRecommendation."""
        from options_arena.agents.synthesis_agent import SynthesisDeps, run_synthesis

        ctx = _make_market_context()
        score = _make_ticker_score()
        contract = _make_contract()
        trend = TrendAssessment(
            **_ASSESSMENT_DEFAULTS,
            trend_strength=0.8,
        )
        vol = VolatilityAssessment(**_ASSESSMENT_DEFAULTS)

        deps = SynthesisDeps(
            context=ctx,
            assessments=[trend, vol],
            contracts=[contract],
            ticker_score=score,
        )

        result = await run_synthesis(deps, model=None, timeout=10.0)

        assert isinstance(result, PositionRecommendation)
        assert result.model_used == "data-driven-fallback"
        assert result.direction == SignalDirection.NEUTRAL
        assert result.confidence <= 0.3
        assert len(result.key_factors) >= 1
        assert result.ticker == "AAPL"

    @pytest.mark.asyncio
    async def test_synthesis_with_mixed_assessment_types(self) -> None:
        """Fallback handles 4+ different assessment subclasses correctly."""
        from options_arena.agents.synthesis_agent import SynthesisDeps, run_synthesis

        ctx = _make_market_context()
        score = _make_ticker_score()
        contract = _make_contract()

        assessments: list[AnyAssessment] = [
            TrendAssessment(**_ASSESSMENT_DEFAULTS, trend_strength=0.8),
            VolatilityAssessment(**_ASSESSMENT_DEFAULTS),
            FlowAssessment(**_ASSESSMENT_DEFAULTS, flow_bias="net call buying"),
            FundamentalAssessment(**_ASSESSMENT_DEFAULTS),
            RiskDeskAssessment(
                **{**_ASSESSMENT_DEFAULTS, "direction": SignalDirection.NEUTRAL},
                max_position_pct=0.05,
            ),
            ContrarianAssessment(
                **{**_ASSESSMENT_DEFAULTS, "direction": SignalDirection.BEARISH},
                consensus_challenged="Overly bullish consensus",
            ),
        ]

        deps = SynthesisDeps(
            context=ctx,
            assessments=assessments,
            contracts=[contract],
            ticker_score=score,
        )

        result = await run_synthesis(deps, model=None, timeout=10.0)

        assert isinstance(result, PositionRecommendation)
        assert result.model_used == "data-driven-fallback"
        # Fallback should reference the assessment count
        factor_text = " ".join(result.key_factors)
        assert "6" in factor_text  # 6 assessments

    def test_recommendation_result_construction(self) -> None:
        """RecommendationResult constructs correctly from components."""
        ctx = _make_market_context()
        trend = TrendAssessment(**_ASSESSMENT_DEFAULTS, trend_strength=0.85)
        vol = VolatilityAssessment(**_ASSESSMENT_DEFAULTS)

        rec = PositionRecommendation(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.75,
            recommended_contract="AAPL 185C 2026-04-15",
            entry_price=Decimal("5.25"),
            entry_criteria="Break above 188",
            exit_criteria="Close below 182",
            position_size_pct=0.05,
            position_rationale="Strong trend alignment",
            risk_reward_ratio=2.5,
            max_loss_estimate="$525 per contract",
            strategy_rationale="Simple long call",
            summary="Bullish setup confirmed by trend and vol desks.",
            key_factors=["Strong momentum", "Low IV rank"],
            risk_assessment="Moderate risk with defined loss",
            model_used="llama-3.3-70b-versatile",
        )

        usage = RunUsage(requests=6, input_tokens=3000, output_tokens=800)

        result = RecommendationResult(
            context=ctx,
            assessments=[trend, vol],
            recommendation=rec,
            total_usage=usage,
            duration_ms=4500,
            is_fallback=False,
            citation_density=0.65,
        )

        assert result.context.ticker == "AAPL"
        assert len(result.assessments) == 2
        assert isinstance(result.assessments[0], TrendAssessment)
        assert isinstance(result.assessments[1], VolatilityAssessment)
        assert result.recommendation.confidence == pytest.approx(0.75, abs=0.01)
        assert result.duration_ms == 4500
        assert result.is_fallback is False
        assert result.citation_density == pytest.approx(0.65, abs=0.01)
        assert result.total_usage.requests == 6
        assert result.total_usage.input_tokens == 3000
        assert result.total_usage.output_tokens == 800
