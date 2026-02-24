"""Shared fixtures for agent unit tests."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from options_arena.agents._parsing import DebateDeps
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    DividendSource,
    ExerciseStyle,
    IndicatorSignals,
    MacdSignal,
    MarketContext,
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


@pytest.fixture()
def mock_market_context() -> MarketContext:
    """Realistic MarketContext for AAPL."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def mock_ticker_score() -> TickerScore:
    """Realistic TickerScore for AAPL with bullish direction."""
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


@pytest.fixture()
def mock_option_contract() -> OptionContract:
    """Realistic OptionContract for AAPL call with Greeks."""
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


@pytest.fixture()
def mock_quote() -> Quote:
    """Realistic Quote for AAPL."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def mock_ticker_info() -> TickerInfo:
    """Realistic TickerInfo for AAPL."""
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


@pytest.fixture()
def mock_debate_deps(
    mock_market_context: MarketContext,
    mock_ticker_score: TickerScore,
    mock_option_contract: OptionContract,
) -> DebateDeps:
    """DebateDeps with context, score, and one contract."""
    return DebateDeps(
        context=mock_market_context,
        ticker_score=mock_ticker_score,
        contracts=[mock_option_contract],
    )


@pytest.fixture()
def mock_debate_config() -> DebateConfig:
    """DebateConfig with reduced timeouts for fast tests."""
    return DebateConfig(
        ollama_timeout=10.0,
        max_total_duration=30.0,
    )


@pytest.fixture()
def mock_agent_response() -> AgentResponse:
    """Realistic AgentResponse for test assertions."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up", "Volume increasing"],
        risks_cited=["Earnings next week"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


@pytest.fixture()
def mock_trade_thesis() -> TradeThesis:
    """Realistic TradeThesis for test assertions."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case supported by momentum indicators.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up", "Sector strength"],
        risk_assessment="Moderate risk. Position sizing: 2% of portfolio.",
        recommended_strategy=None,
    )
