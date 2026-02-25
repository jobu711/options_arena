"""Integration tests for the AI debate system end-to-end.

These tests verify the full debate pipeline without requiring a Groq API key.
They test that the fallback path produces a valid result from real model
construction through to DebateResult, exercising real code paths.

All tests marked @pytest.mark.integration.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic_ai import models

from options_arena.agents._parsing import DebateResult
from options_arena.agents.orchestrator import run_debate
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
    TradeThesis,
)

# Prevent accidental real API calls — guarantees fallback path regardless of Groq API key
models.ALLOW_MODEL_REQUESTS = False


def _make_ticker_score() -> TickerScore:
    return TickerScore(
        ticker="NVDA",
        composite_score=85.0,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(
            rsi=68.0,
            adx=35.0,
            sma_alignment=0.9,
            bb_width=30.0,
            atr_pct=20.0,
            obv=70.0,
            relative_volume=65.0,
        ),
        scan_run_id=1,
    )


def _make_quote() -> Quote:
    return Quote(
        ticker="NVDA",
        price=Decimal("850.00"),
        bid=Decimal("849.90"),
        ask=Decimal("850.10"),
        volume=50_000_000,
        timestamp=datetime(2026, 2, 24, 15, 0, 0, tzinfo=UTC),
    )


def _make_ticker_info() -> TickerInfo:
    return TickerInfo(
        ticker="NVDA",
        company_name="NVIDIA Corporation",
        sector="Information Technology",
        market_cap=2_100_000_000_000,
        dividend_yield=0.0002,
        dividend_source=DividendSource.FORWARD,
        current_price=Decimal("850.00"),
        fifty_two_week_high=Decimal("950.00"),
        fifty_two_week_low=Decimal("450.00"),
    )


def _make_contract() -> OptionContract:
    return OptionContract(
        ticker="NVDA",
        option_type=OptionType.CALL,
        strike=Decimal("870.00"),
        expiration=date.today() + timedelta(days=30),
        bid=Decimal("15.00"),
        ask=Decimal("16.00"),
        last=Decimal("15.50"),
        volume=5000,
        open_interest=20000,
        exercise_style=ExerciseStyle.AMERICAN,
        market_iv=0.45,
        greeks=OptionGreeks(
            delta=0.32,
            gamma=0.003,
            theta=-0.85,
            vega=1.20,
            rho=0.15,
            pricing_model=PricingModel.BAW,
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_debate_fallback_without_llm() -> None:
    """Full debate pipeline without LLM provider produces valid fallback result.

    Groq API is not available in CI, so the debate should fall back to data-driven
    analysis. This tests the complete path from run_debate through to DebateResult.
    """
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
    assert isinstance(result.bull_response, AgentResponse)
    assert isinstance(result.bear_response, AgentResponse)
    assert isinstance(result.thesis, TradeThesis)
    assert result.thesis.confidence == pytest.approx(0.3)
    assert result.duration_ms >= 0


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fallback_thesis_direction_matches_score() -> None:
    """Fallback thesis direction matches the ticker score direction."""
    config = DebateConfig(agent_timeout=0.5, max_total_duration=1.0)
    score = _make_ticker_score()
    result = await run_debate(
        ticker_score=score,
        contracts=[_make_contract()],
        quote=_make_quote(),
        ticker_info=_make_ticker_info(),
        config=config,
    )
    assert result.thesis.direction == score.direction


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fallback_with_empty_contracts() -> None:
    """Fallback works when no contracts are available."""
    config = DebateConfig(agent_timeout=0.5, max_total_duration=1.0)
    result = await run_debate(
        ticker_score=_make_ticker_score(),
        contracts=[],
        quote=_make_quote(),
        ticker_info=_make_ticker_info(),
        config=config,
    )
    assert isinstance(result, DebateResult)
    assert result.is_fallback is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fallback_model_used_is_data_driven() -> None:
    """Fallback agent responses use 'data-driven-fallback' as model_used."""
    config = DebateConfig(agent_timeout=0.5, max_total_duration=1.0)
    result = await run_debate(
        ticker_score=_make_ticker_score(),
        contracts=[_make_contract()],
        quote=_make_quote(),
        ticker_info=_make_ticker_info(),
        config=config,
    )
    assert result.bull_response.model_used == "data-driven-fallback"
    assert result.bear_response.model_used == "data-driven-fallback"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_fallback_bull_confidence_bounded() -> None:
    """Fallback bull confidence is bounded by composite score."""
    config = DebateConfig(agent_timeout=0.5, max_total_duration=1.0)
    result = await run_debate(
        ticker_score=_make_ticker_score(),
        contracts=[_make_contract()],
        quote=_make_quote(),
        ticker_info=_make_ticker_info(),
        config=config,
    )
    assert 0.0 <= result.bull_response.confidence <= 0.3
