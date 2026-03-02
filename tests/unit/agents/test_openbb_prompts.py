"""Tests for OpenBB enrichment sections in render_context_block().

Tests cover:
  - Fundamental Profile section renders when fields are populated
  - Fundamental Profile omitted when all fields are None
  - Partial fundamentals render only non-None fields
  - P/E, revenue growth, profit margin formatting
  - Unusual Options Flow section renders when fields are populated
  - Flow section omitted when all flow fields None
  - Net premium comma formatting
  - News Sentiment section renders with headlines
  - Sentiment section omitted when news_sentiment is None
  - Headlines truncated to 5
  - No headlines still renders aggregate
  - Backward compat: no OpenBB data → zero new sections
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from options_arena.agents._parsing import render_context_block
from options_arena.models import ExerciseStyle, MacdSignal, MarketContext


def _make_context(**overrides: object) -> MarketContext:
    """Build a MarketContext with sensible defaults."""
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


# ---------------------------------------------------------------------------
# Fundamental Profile section
# ---------------------------------------------------------------------------


class TestRenderFundamentalSection:
    """Tests for ## Fundamental Profile section in context block."""

    def test_all_fundamentals_present(self) -> None:
        """Section rendered with all 7 fields when all populated."""
        ctx = _make_context(
            pe_ratio=28.5,
            forward_pe=24.1,
            peg_ratio=1.8,
            price_to_book=12.3,
            debt_to_equity=1.52,
            revenue_growth=0.128,
            profit_margin=0.26,
        )
        block = render_context_block(ctx)
        assert "## Fundamental Profile" in block
        assert "P/E: 28.5" in block
        assert "FORWARD P/E: 24.1" in block
        assert "PEG: 1.80" in block
        assert "P/B: 12.30" in block
        assert "DEBT/EQUITY: 1.52" in block
        assert "REVENUE GROWTH: 12.8%" in block
        assert "PROFIT MARGIN: 26.0%" in block

    def test_partial_fundamentals(self) -> None:
        """Only non-None fields rendered."""
        ctx = _make_context(pe_ratio=28.5, forward_pe=24.1)
        block = render_context_block(ctx)
        assert "## Fundamental Profile" in block
        assert "P/E: 28.5" in block
        assert "FORWARD P/E: 24.1" in block
        assert "PEG:" not in block
        assert "DEBT/EQUITY:" not in block

    def test_no_fundamentals(self) -> None:
        """Section omitted entirely when all fundamental fields are None."""
        ctx = _make_context()
        block = render_context_block(ctx)
        assert "## Fundamental Profile" not in block

    def test_pe_ratio_formatting(self) -> None:
        """P/E renders with one decimal place."""
        ctx = _make_context(pe_ratio=28.456)
        block = render_context_block(ctx)
        assert "P/E: 28.5" in block

    def test_revenue_growth_percentage(self) -> None:
        """Revenue growth 0.128 renders as 12.8%."""
        ctx = _make_context(revenue_growth=0.128)
        block = render_context_block(ctx)
        assert "REVENUE GROWTH: 12.8%" in block

    def test_negative_revenue_growth(self) -> None:
        """Negative revenue growth renders correctly."""
        ctx = _make_context(revenue_growth=-0.05)
        block = render_context_block(ctx)
        assert "REVENUE GROWTH: -5.0%" in block


# ---------------------------------------------------------------------------
# Unusual Options Flow section
# ---------------------------------------------------------------------------


class TestRenderFlowSection:
    """Tests for ## Unusual Options Flow section in context block."""

    def test_all_flow_present(self) -> None:
        """Section rendered with all 3 fields."""
        ctx = _make_context(
            net_call_premium=4_200_000.0,
            net_put_premium=1_800_000.0,
            options_put_call_ratio=0.49,
        )
        block = render_context_block(ctx)
        assert "## Unusual Options Flow" in block
        assert "NET CALL PREMIUM ($): 4,200,000" in block
        assert "NET PUT PREMIUM ($): 1,800,000" in block
        assert "OPTIONS PUT/CALL RATIO: 0.49" in block

    def test_no_flow(self) -> None:
        """Section omitted when all flow fields None."""
        ctx = _make_context()
        block = render_context_block(ctx)
        assert "## Unusual Options Flow" not in block

    def test_premium_formatting(self) -> None:
        """Large net premium renders with comma separators."""
        ctx = _make_context(net_call_premium=12_345_678.0)
        block = render_context_block(ctx)
        assert "NET CALL PREMIUM ($): 12,345,678" in block

    def test_partial_flow(self) -> None:
        """Only non-None flow fields rendered."""
        ctx = _make_context(options_put_call_ratio=0.65)
        block = render_context_block(ctx)
        assert "## Unusual Options Flow" in block
        assert "OPTIONS PUT/CALL RATIO: 0.65" in block
        assert "NET CALL PREMIUM" not in block


# ---------------------------------------------------------------------------
# News Sentiment section
# ---------------------------------------------------------------------------


class TestRenderSentimentSection:
    """Tests for ## News Sentiment section in context block."""

    def test_bullish_sentiment(self) -> None:
        """Renders 'Aggregate: Bullish (+0.42)' with headlines."""
        ctx = _make_context(
            news_sentiment=0.42,
            news_sentiment_label="bullish",
            recent_headlines=["Apple beats earnings", "Strong iPhone sales"],
        )
        block = render_context_block(ctx)
        assert "## News Sentiment" in block
        assert "AGGREGATE: Bullish (+0.42)" in block
        assert '- "Apple beats earnings"' in block
        assert '- "Strong iPhone sales"' in block

    def test_bearish_sentiment(self) -> None:
        """Renders 'Aggregate: Bearish (-0.65)'."""
        ctx = _make_context(
            news_sentiment=-0.65,
            news_sentiment_label="bearish",
            recent_headlines=["Supply chain concerns"],
        )
        block = render_context_block(ctx)
        assert "AGGREGATE: Bearish (-0.65)" in block

    def test_no_sentiment(self) -> None:
        """Section omitted when news_sentiment is None."""
        ctx = _make_context()
        block = render_context_block(ctx)
        assert "## News Sentiment" not in block

    def test_headlines_truncated_to_five(self) -> None:
        """Only first 5 headlines rendered."""
        ctx = _make_context(
            news_sentiment=0.3,
            news_sentiment_label="bullish",
            recent_headlines=[f"Headline {i}" for i in range(8)],
        )
        block = render_context_block(ctx)
        assert '- "Headline 0"' in block
        assert '- "Headline 4"' in block
        assert '- "Headline 5"' not in block

    def test_no_headlines(self) -> None:
        """Sentiment section without headlines still renders aggregate."""
        ctx = _make_context(
            news_sentiment=0.1,
            news_sentiment_label="neutral",
            recent_headlines=[],
        )
        block = render_context_block(ctx)
        assert "## News Sentiment" in block
        assert "AGGREGATE: Neutral (+0.10)" in block

    def test_neutral_label_default(self) -> None:
        """When news_sentiment_label is None, defaults to 'neutral'."""
        ctx = _make_context(news_sentiment=0.02)
        block = render_context_block(ctx)
        assert "AGGREGATE: Neutral (+0.02)" in block


# ---------------------------------------------------------------------------
# Backward compat
# ---------------------------------------------------------------------------


class TestRenderContextBlockBackwardCompat:
    """Tests for backward compatibility — no OpenBB data."""

    def test_no_openbb_data_no_new_sections(self) -> None:
        """MarketContext without OpenBB fields renders no new sections."""
        ctx = _make_context()
        block = render_context_block(ctx)
        assert "## Fundamental Profile" not in block
        assert "## Unusual Options Flow" not in block
        assert "## News Sentiment" not in block

    def test_existing_fields_still_present(self) -> None:
        """Core fields still rendered correctly."""
        ctx = _make_context()
        block = render_context_block(ctx)
        assert "TICKER: AAPL" in block
        assert "PRICE: $185.50" in block
        assert "RSI(14): 62.3" in block
        assert "IV RANK: 45.2" in block
