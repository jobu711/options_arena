"""Tests for MarketContext OpenBB enrichment fields and build_market_context wiring.

Tests cover:
  - New MarketContext OpenBB fields default to None (backward compat)
  - enrichment_ratio() returns 0.0 when all OpenBB fields are None
  - enrichment_ratio() returns 1.0 when all 11 float fields populated
  - enrichment_ratio() returns correct fraction for partial data
  - completeness_ratio() unchanged by new OpenBB fields
  - NaN/Inf rejected in new OpenBB float fields
  - build_market_context without OpenBB data (backward compat)
  - build_market_context with fundamentals, flow, sentiment snapshots
  - build_market_context with partial fundamentals
  - build_market_context truncates headlines to 5
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from options_arena.agents.orchestrator import build_market_context
from options_arena.models import (
    FundamentalSnapshot,
    MacdSignal,
    MarketContext,
    NewsSentimentSnapshot,
    OptionContract,
    Quote,
    SentimentLabel,
    TickerInfo,
    TickerScore,
    UnusualFlowSnapshot,
)
from options_arena.models.openbb import NewsHeadline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(**overrides: object) -> MarketContext:
    """Build a MarketContext with sensible defaults, allowing field overrides."""
    from decimal import Decimal

    from options_arena.models import ExerciseStyle

    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.50"),
        "price_52w_high": Decimal("199.62"),
        "price_52w_low": Decimal("164.08"),
        "iv_rank": 45.2,
        "iv_percentile": 52.1,
        "atm_iv_30d": 28.5,
        "rsi_14": 62.3,
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "put_call_ratio": 0.85,
        "next_earnings": None,
        "dte_target": 45,
        "target_strike": Decimal("190.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return MarketContext(**defaults)  # type: ignore[arg-type]


def _make_fundamentals(**overrides: object) -> FundamentalSnapshot:
    """Build a FundamentalSnapshot with defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "pe_ratio": 28.5,
        "forward_pe": 24.1,
        "peg_ratio": 1.8,
        "price_to_book": 12.3,
        "debt_to_equity": 1.52,
        "revenue_growth": 0.128,
        "profit_margin": 0.26,
        "market_cap": 2_800_000_000_000,
        "fetched_at": datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return FundamentalSnapshot(**defaults)  # type: ignore[arg-type]


def _make_flow(**overrides: object) -> UnusualFlowSnapshot:
    """Build an UnusualFlowSnapshot with defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "net_call_premium": 4_200_000.0,
        "net_put_premium": 1_800_000.0,
        "call_volume": 85_000,
        "put_volume": 42_000,
        "put_call_ratio": 0.49,
        "fetched_at": datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return UnusualFlowSnapshot(**defaults)  # type: ignore[arg-type]


def _make_sentiment(**overrides: object) -> NewsSentimentSnapshot:
    """Build a NewsSentimentSnapshot with defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "headlines": [
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
        "aggregate_sentiment": 0.42,
        "sentiment_label": SentimentLabel.BULLISH,
        "article_count": 2,
        "fetched_at": datetime(2026, 2, 24, 14, 0, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return NewsSentimentSnapshot(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MarketContext OpenBB fields
# ---------------------------------------------------------------------------


class TestMarketContextEnrichment:
    """Tests for new OpenBB enrichment fields on MarketContext."""

    def test_new_fields_default_none(self) -> None:
        """All OpenBB fields default to None — backward compatible."""
        ctx = _make_context()
        assert ctx.pe_ratio is None
        assert ctx.forward_pe is None
        assert ctx.peg_ratio is None
        assert ctx.price_to_book is None
        assert ctx.debt_to_equity is None
        assert ctx.revenue_growth is None
        assert ctx.profit_margin is None
        assert ctx.net_call_premium is None
        assert ctx.net_put_premium is None
        assert ctx.options_put_call_ratio is None
        assert ctx.news_sentiment is None
        assert ctx.news_sentiment_label is None
        assert ctx.recent_headlines is None

    def test_enrichment_ratio_all_none(self) -> None:
        """enrichment_ratio() returns 0.0 when all OpenBB fields are None."""
        ctx = _make_context()
        assert ctx.enrichment_ratio() == pytest.approx(0.0)

    def test_enrichment_ratio_all_populated(self) -> None:
        """enrichment_ratio() returns 1.0 when all 11 float fields populated."""
        ctx = _make_context(
            pe_ratio=28.5,
            forward_pe=24.1,
            peg_ratio=1.8,
            price_to_book=12.3,
            debt_to_equity=1.52,
            revenue_growth=0.128,
            profit_margin=0.26,
            net_call_premium=4_200_000.0,
            net_put_premium=1_800_000.0,
            options_put_call_ratio=0.49,
            news_sentiment=0.42,
        )
        assert ctx.enrichment_ratio() == pytest.approx(1.0)

    def test_enrichment_ratio_partial(self) -> None:
        """enrichment_ratio() returns correct fraction for partial data."""
        ctx = _make_context(
            pe_ratio=28.5,
            forward_pe=24.1,
            news_sentiment=0.42,
        )
        # 3 of 11 enrichment fields populated
        assert ctx.enrichment_ratio() == pytest.approx(3 / 11)

    def test_completeness_ratio_unchanged(self) -> None:
        """completeness_ratio() ignores OpenBB fields — same denominator as before."""
        ctx_without = _make_context()
        ctx_with = _make_context(
            pe_ratio=28.5,
            forward_pe=24.1,
            news_sentiment=0.42,
        )
        assert ctx_without.completeness_ratio() == pytest.approx(
            ctx_with.completeness_ratio()
        )

    def test_nan_rejected_in_pe_ratio(self) -> None:
        """NaN in pe_ratio raises ValidationError."""
        with pytest.raises(Exception, match="must be finite"):
            _make_context(pe_ratio=float("nan"))

    def test_inf_rejected_in_debt_to_equity(self) -> None:
        """Inf in debt_to_equity raises ValidationError."""
        with pytest.raises(Exception, match="must be finite"):
            _make_context(debt_to_equity=float("inf"))

    def test_nan_rejected_in_news_sentiment(self) -> None:
        """NaN in news_sentiment raises ValidationError."""
        with pytest.raises(Exception, match="must be finite"):
            _make_context(news_sentiment=float("nan"))

    def test_negative_pe_allowed(self) -> None:
        """Negative P/E is valid (loss-making companies)."""
        ctx = _make_context(pe_ratio=-5.2)
        assert ctx.pe_ratio == pytest.approx(-5.2)

    def test_negative_news_sentiment_allowed(self) -> None:
        """Negative news_sentiment is valid (range -1.0 to 1.0)."""
        ctx = _make_context(news_sentiment=-0.65)
        assert ctx.news_sentiment == pytest.approx(-0.65)


# ---------------------------------------------------------------------------
# build_market_context with OpenBB data
# ---------------------------------------------------------------------------


class TestBuildMarketContextOpenBB:
    """Tests for build_market_context() OpenBB parameter wiring."""

    def test_without_openbb_data(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """build_market_context() without OpenBB kwargs → all OpenBB fields None."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.pe_ratio is None
        assert ctx.forward_pe is None
        assert ctx.news_sentiment is None
        assert ctx.net_call_premium is None
        assert ctx.recent_headlines is None

    def test_with_fundamentals(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Fundamentals mapped correctly to MarketContext fields."""
        fund = _make_fundamentals()
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            fundamentals=fund,
        )
        assert ctx.pe_ratio == pytest.approx(28.5)
        assert ctx.forward_pe == pytest.approx(24.1)
        assert ctx.peg_ratio == pytest.approx(1.8)
        assert ctx.price_to_book == pytest.approx(12.3)
        assert ctx.debt_to_equity == pytest.approx(1.52)
        assert ctx.revenue_growth == pytest.approx(0.128)
        assert ctx.profit_margin == pytest.approx(0.26)

    def test_with_flow(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Flow data mapped correctly."""
        fl = _make_flow()
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            flow=fl,
        )
        assert ctx.net_call_premium == pytest.approx(4_200_000.0)
        assert ctx.net_put_premium == pytest.approx(1_800_000.0)
        assert ctx.options_put_call_ratio == pytest.approx(0.49)

    def test_with_sentiment(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Sentiment mapped correctly, headlines present."""
        sent = _make_sentiment()
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            sentiment=sent,
        )
        assert ctx.news_sentiment == pytest.approx(0.42)
        assert ctx.news_sentiment_label == "bullish"
        assert ctx.recent_headlines is not None
        assert len(ctx.recent_headlines) == 2
        assert "Apple beats Q4 earnings expectations" in ctx.recent_headlines[0]

    def test_with_all_openbb_data(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """All three OpenBB sources provided."""
        fund = _make_fundamentals()
        fl = _make_flow()
        sent = _make_sentiment()
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            fundamentals=fund, flow=fl, sentiment=sent,
        )
        assert ctx.pe_ratio is not None
        assert ctx.net_call_premium is not None
        assert ctx.news_sentiment is not None
        assert ctx.enrichment_ratio() == pytest.approx(1.0)

    def test_partial_fundamentals(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """FundamentalSnapshot with some None fields → corresponding context fields None."""
        fund = _make_fundamentals(
            pe_ratio=28.5,
            forward_pe=None,
            peg_ratio=None,
            price_to_book=None,
            debt_to_equity=None,
            revenue_growth=None,
            profit_margin=None,
        )
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            fundamentals=fund,
        )
        assert ctx.pe_ratio == pytest.approx(28.5)
        assert ctx.forward_pe is None
        assert ctx.peg_ratio is None

    def test_headlines_truncated_to_five(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """recent_headlines truncated to 5 when more than 5 headlines."""
        headlines = [
            NewsHeadline(
                title=f"Headline {i}",
                published_at=datetime(2026, 2, 24, 10, 0, 0, tzinfo=UTC),
                sentiment_score=0.3,
                source="Test",
            )
            for i in range(8)
        ]
        sent = _make_sentiment(headlines=headlines, article_count=8)
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            sentiment=sent,
        )
        assert ctx.recent_headlines is not None
        assert len(ctx.recent_headlines) == 5

    def test_empty_headlines_returns_none(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Empty headlines list → recent_headlines is None."""
        sent = _make_sentiment(headlines=[], article_count=0)
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract],
            sentiment=sent,
        )
        assert ctx.recent_headlines is None
