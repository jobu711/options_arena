"""Integration tests for OpenBB enrichment in the debate path.

Tests verify end-to-end wiring with mocked external dependencies:
  - Debate with OpenBB data → enriched context includes fundamentals/flow/sentiment
  - Debate without OpenBB data → identical to pre-integration behavior
  - Partial OpenBB failure → surviving data still populates context
  - Context block rendering includes OpenBB sections when data present
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import render_context_block
from options_arena.agents.bear import bear_agent
from options_arena.agents.bull import bull_agent
from options_arena.agents.orchestrator import build_market_context
from options_arena.agents.risk import risk_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    DebateConfig,
    DividendSource,
    ExerciseStyle,
    FundamentalSnapshot,
    IndicatorSignals,
    NewsSentimentSnapshot,
    OptionContract,
    OptionGreeks,
    OptionType,
    PricingModel,
    Quote,
    SentimentLabel,
    SignalDirection,
    TickerInfo,
    TickerScore,
    UnusualFlowSnapshot,
)
from options_arena.models.openbb import NewsHeadline

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ticker_score() -> TickerScore:
    """Scored AAPL with bullish direction."""
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
            relative_volume=55.0,
        ),
        scan_run_id=1,
    )


@pytest.fixture()
def quote() -> Quote:
    """AAPL quote."""
    return Quote(
        ticker="AAPL",
        price=Decimal("185.50"),
        bid=Decimal("185.48"),
        ask=Decimal("185.52"),
        volume=42_000_000,
        timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture()
def ticker_info() -> TickerInfo:
    """AAPL ticker info."""
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
def contract() -> OptionContract:
    """AAPL call contract with Greeks."""
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
def fundamentals() -> FundamentalSnapshot:
    """OpenBB fundamental snapshot."""
    return FundamentalSnapshot(
        ticker="AAPL",
        pe_ratio=28.5,
        forward_pe=24.1,
        peg_ratio=1.8,
        price_to_book=12.3,
        debt_to_equity=1.52,
        revenue_growth=0.128,
        profit_margin=0.26,
        market_cap=2_800_000_000_000,
        fetched_at=datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    )


@pytest.fixture()
def flow() -> UnusualFlowSnapshot:
    """OpenBB flow snapshot."""
    return UnusualFlowSnapshot(
        ticker="AAPL",
        net_call_premium=4_200_000.0,
        net_put_premium=1_800_000.0,
        call_volume=85_000,
        put_volume=42_000,
        put_call_ratio=0.49,
        fetched_at=datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    )


@pytest.fixture()
def sentiment() -> NewsSentimentSnapshot:
    """OpenBB news sentiment snapshot."""
    return NewsSentimentSnapshot(
        ticker="AAPL",
        headlines=[
            NewsHeadline(
                title="Apple beats Q4 earnings expectations",
                published_at=datetime(2026, 2, 24, 10, 0, 0, tzinfo=UTC),
                sentiment_score=0.72,
                source="Reuters",
            ),
            NewsHeadline(
                title="iPhone sales strong in emerging markets",
                published_at=datetime(2026, 2, 24, 9, 0, 0, tzinfo=UTC),
                sentiment_score=0.45,
                source="Bloomberg",
            ),
        ],
        aggregate_sentiment=0.42,
        sentiment_label=SentimentLabel.BULLISH,
        article_count=2,
        fetched_at=datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestOpenBBDebateIntegration:
    """Integration tests for the debate path with OpenBB enrichment."""

    @pytest.mark.asyncio
    async def test_debate_with_openbb_data(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        fundamentals: FundamentalSnapshot,
        flow: UnusualFlowSnapshot,
        sentiment: NewsSentimentSnapshot,
    ) -> None:
        """Full debate with mocked OpenBB → enriched context, valid result."""
        from options_arena.agents.orchestrator import run_debate

        config = DebateConfig(
            api_key="test-key",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )

        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score,
                [contract],
                quote,
                ticker_info,
                config,
                fundamentals=fundamentals,
                flow=flow,
                sentiment=sentiment,
            )

        assert result is not None
        # Context should have OpenBB data
        assert result.context.pe_ratio == pytest.approx(28.5)
        assert result.context.net_call_premium == pytest.approx(4_200_000.0)
        assert result.context.news_sentiment == pytest.approx(0.42)
        assert result.context.enrichment_ratio() == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_debate_without_openbb(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
    ) -> None:
        """Debate with no OpenBB data → identical to pre-integration behavior."""
        from options_arena.agents.orchestrator import run_debate

        config = DebateConfig(
            api_key="test-key",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )

        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score,
                [contract],
                quote,
                ticker_info,
                config,
            )

        assert result is not None
        assert result.context.pe_ratio is None
        assert result.context.news_sentiment is None
        assert result.context.enrichment_ratio() == pytest.approx(0.0)

    def test_context_block_includes_fundamentals(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        fundamentals: FundamentalSnapshot,
    ) -> None:
        """render_context_block output includes '## Fundamental Profile' section."""
        ctx = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            [contract],
            fundamentals=fundamentals,
        )
        block = render_context_block(ctx)
        assert "## Fundamental Profile" in block
        assert "P/E: 28.5" in block
        assert "REVENUE GROWTH: 12.8%" in block

    def test_context_block_includes_flow(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        flow: UnusualFlowSnapshot,
    ) -> None:
        """render_context_block output includes '## Unusual Options Flow' section."""
        ctx = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            [contract],
            flow=flow,
        )
        block = render_context_block(ctx)
        assert "## Unusual Options Flow" in block
        assert "NET CALL PREMIUM ($): 4,200,000" in block

    def test_context_block_includes_sentiment(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
        sentiment: NewsSentimentSnapshot,
    ) -> None:
        """render_context_block includes '## News Sentiment' with headlines."""
        ctx = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            [contract],
            sentiment=sentiment,
        )
        block = render_context_block(ctx)
        assert "## News Sentiment" in block
        assert "Bullish (+0.42)" in block
        assert '"Apple beats Q4 earnings expectations"' in block

    def test_context_block_no_openbb_sections_without_data(
        self,
        ticker_score: TickerScore,
        contract: OptionContract,
        quote: Quote,
        ticker_info: TickerInfo,
    ) -> None:
        """No OpenBB data → no new sections in context block."""
        ctx = build_market_context(
            ticker_score,
            quote,
            ticker_info,
            [contract],
        )
        block = render_context_block(ctx)
        assert "## Fundamental Profile" not in block
        assert "## Unusual Options Flow" not in block
        assert "## News Sentiment" not in block
