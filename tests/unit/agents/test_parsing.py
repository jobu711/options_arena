"""Tests for _parsing.py — DebateDeps, DebateResult, render_context_block, strip_think_tags.

Tests cover:
  - DebateDeps construction with required fields
  - DebateDeps optional fields (opponent_argument, bull_response, bear_response, vol_response)
  - DebateResult construction
  - DebateResult field access (including vol_response default)
  - render_context_block output format
  - render_context_block contains expected field labels
  - render_context_block renders all MarketContext fields
  - strip_think_tags removes full blocks, stray tags, and nested content
"""

from __future__ import annotations

import pytest
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import (
    DebateDeps,
    DebateResult,
    compute_citation_density,
    render_context_block,
    strip_think_tags,
)
from options_arena.models import (
    AgentResponse,
    MarketContext,
    OptionContract,
    SignalDirection,
    SpreadType,
    TickerScore,
    TradeThesis,
    VolatilityThesis,
)

# ---------------------------------------------------------------------------
# DebateDeps
# ---------------------------------------------------------------------------


class TestDebateDeps:
    """Tests for DebateDeps dataclass."""

    def test_construction_with_required_fields(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
    ) -> None:
        """DebateDeps constructs with required fields only."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
        )
        assert deps.context.ticker == "AAPL"
        assert deps.ticker_score.composite_score == pytest.approx(72.5)
        assert len(deps.contracts) == 1

    def test_optional_opponent_argument_defaults_none(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """opponent_argument defaults to None."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
        )
        assert deps.opponent_argument is None

    def test_optional_bull_response_defaults_none(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """bull_response defaults to None."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
        )
        assert deps.bull_response is None

    def test_optional_bear_response_defaults_none(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """bear_response defaults to None."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
        )
        assert deps.bear_response is None

    def test_can_set_opponent_argument(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """opponent_argument can be set to a string."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
            opponent_argument="RSI indicates strong momentum.",
        )
        assert deps.opponent_argument == "RSI indicates strong momentum."

    def test_can_set_bull_response(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
        mock_agent_response: AgentResponse,
    ) -> None:
        """bull_response can be set to an AgentResponse."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
            bull_response=mock_agent_response,
        )
        assert deps.bull_response is not None
        assert isinstance(deps.bull_response, AgentResponse)

    def test_can_set_bear_response(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """bear_response can be set to an AgentResponse."""
        bear = AgentResponse(
            agent_name="bear",
            direction=SignalDirection.BEARISH,
            confidence=0.6,
            argument="IV is elevated.",
            key_points=["IV high"],
            risks_cited=["Reversal possible"],
            contracts_referenced=["AAPL $190 CALL"],
            model_used="test",
        )
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
            bear_response=bear,
        )
        assert deps.bear_response is not None

    def test_optional_vol_response_defaults_none(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """vol_response defaults to None."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
        )
        assert deps.vol_response is None

    def test_can_set_vol_response(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """vol_response can be set to a VolatilityThesis."""
        vol = VolatilityThesis(
            iv_assessment="overpriced",
            iv_rank_interpretation="IV rank at 85 is in the top 15%",
            confidence=0.75,
            recommended_strategy=SpreadType.IRON_CONDOR,
            strategy_rationale="High IV favors selling premium",
            target_iv_entry=85.0,
            target_iv_exit=50.0,
            suggested_strikes=["185C", "195C"],
            key_vol_factors=["Earnings in 5 days", "IV rank 85"],
            model_used="llama3.1:8b",
        )
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
            vol_response=vol,
        )
        assert deps.vol_response is not None
        assert isinstance(deps.vol_response, VolatilityThesis)
        assert deps.vol_response.iv_assessment == "overpriced"

    def test_empty_contracts_list(
        self,
        mock_market_context: MarketContext,
        mock_ticker_score: TickerScore,
    ) -> None:
        """contracts can be an empty list."""
        deps = DebateDeps(
            context=mock_market_context,
            ticker_score=mock_ticker_score,
            contracts=[],
        )
        assert deps.contracts == []


# ---------------------------------------------------------------------------
# DebateResult
# ---------------------------------------------------------------------------


class TestDebateResult:
    """Tests for DebateResult dataclass."""

    def test_construction(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """DebateResult constructs with all fields."""
        bear = AgentResponse(
            agent_name="bear",
            direction=SignalDirection.BEARISH,
            confidence=0.55,
            argument="Bearish case.",
            key_points=["Point A"],
            risks_cited=["Risk A"],
            contracts_referenced=[],
            model_used="test",
        )
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=bear,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1500,
            is_fallback=False,
        )
        assert result.context.ticker == "AAPL"
        assert isinstance(result.bull_response, AgentResponse)
        assert isinstance(result.bear_response, AgentResponse)
        assert isinstance(result.thesis, TradeThesis)
        assert result.duration_ms == 1500
        assert result.is_fallback is False

    def test_fallback_flag(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """DebateResult tracks is_fallback correctly."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=500,
            is_fallback=True,
        )
        assert result.is_fallback is True

    def test_vol_response_defaults_none(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """vol_response defaults to None when not provided."""
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1500,
            is_fallback=False,
        )
        assert result.vol_response is None

    def test_vol_response_can_be_set(
        self,
        mock_market_context: MarketContext,
        mock_agent_response: AgentResponse,
        mock_trade_thesis: TradeThesis,
    ) -> None:
        """vol_response can be set to a VolatilityThesis."""
        vol = VolatilityThesis(
            iv_assessment="overpriced",
            iv_rank_interpretation="IV rank at 85 is in the top 15%",
            confidence=0.75,
            recommended_strategy=SpreadType.IRON_CONDOR,
            strategy_rationale="High IV favors selling premium",
            target_iv_entry=85.0,
            target_iv_exit=50.0,
            suggested_strikes=["185C", "195C"],
            key_vol_factors=["Earnings in 5 days", "IV rank 85"],
            model_used="llama3.1:8b",
        )
        result = DebateResult(
            context=mock_market_context,
            bull_response=mock_agent_response,
            bear_response=mock_agent_response,
            thesis=mock_trade_thesis,
            total_usage=RunUsage(),
            duration_ms=1500,
            is_fallback=False,
            vol_response=vol,
        )
        assert result.vol_response is not None
        assert isinstance(result.vol_response, VolatilityThesis)
        assert result.vol_response.recommended_strategy == SpreadType.IRON_CONDOR


# ---------------------------------------------------------------------------
# render_context_block
# ---------------------------------------------------------------------------


class TestRenderContextBlock:
    """Tests for render_context_block formatting."""

    def test_contains_ticker(self, mock_market_context: MarketContext) -> None:
        """Output contains TICKER label with value."""
        text = render_context_block(mock_market_context)
        assert "TICKER: AAPL" in text

    def test_contains_price(self, mock_market_context: MarketContext) -> None:
        """Output contains PRICE label."""
        text = render_context_block(mock_market_context)
        assert "PRICE: $185.50" in text

    def test_contains_52w_high(self, mock_market_context: MarketContext) -> None:
        """Output contains 52W HIGH label."""
        text = render_context_block(mock_market_context)
        assert "52W HIGH: $199.62" in text

    def test_contains_52w_low(self, mock_market_context: MarketContext) -> None:
        """Output contains 52W LOW label."""
        text = render_context_block(mock_market_context)
        assert "52W LOW: $164.08" in text

    def test_contains_rsi(self, mock_market_context: MarketContext) -> None:
        """Output contains RSI(14) label."""
        text = render_context_block(mock_market_context)
        assert "RSI(14): 62.3" in text

    def test_contains_macd(self, mock_market_context: MarketContext) -> None:
        """Output contains MACD label."""
        text = render_context_block(mock_market_context)
        assert "MACD: bullish_crossover" in text

    def test_contains_iv_rank(self, mock_market_context: MarketContext) -> None:
        """Output contains IV RANK label."""
        text = render_context_block(mock_market_context)
        assert "IV RANK: 45.2" in text

    def test_contains_iv_percentile(self, mock_market_context: MarketContext) -> None:
        """Output contains IV PERCENTILE label."""
        text = render_context_block(mock_market_context)
        assert "IV PERCENTILE: 52.1" in text

    def test_contains_sector(self, mock_market_context: MarketContext) -> None:
        """Output contains SECTOR label."""
        text = render_context_block(mock_market_context)
        assert "SECTOR: Information Technology" in text

    def test_contains_target_strike(self, mock_market_context: MarketContext) -> None:
        """Output contains TARGET STRIKE label."""
        text = render_context_block(mock_market_context)
        assert "TARGET STRIKE: $190.00" in text

    def test_contains_target_delta(self, mock_market_context: MarketContext) -> None:
        """Output contains TARGET DELTA label."""
        text = render_context_block(mock_market_context)
        assert "TARGET DELTA: 0.35" in text

    def test_contains_dte(self, mock_market_context: MarketContext) -> None:
        """Output contains DTE label."""
        text = render_context_block(mock_market_context)
        assert "DTE: 45" in text

    def test_contains_div_yield(self, mock_market_context: MarketContext) -> None:
        """Output contains DIV YIELD label."""
        text = render_context_block(mock_market_context)
        assert "DIV YIELD: 0.50%" in text

    def test_contains_exercise_style(self, mock_market_context: MarketContext) -> None:
        """Output contains EXERCISE label."""
        text = render_context_block(mock_market_context)
        assert "EXERCISE: american" in text

    def test_output_is_string(self, mock_market_context: MarketContext) -> None:
        """Output is a plain string, not bytes or other type."""
        text = render_context_block(mock_market_context)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# strip_think_tags
# ---------------------------------------------------------------------------


class TestStripThinkTags:
    """Tests for strip_think_tags helper."""

    def test_removes_complete_think_block(self) -> None:
        """Strips <think>content</think> block entirely."""
        assert strip_think_tags("<think>reasoning</think> Answer.") == "Answer."

    def test_removes_multiline_think_block(self) -> None:
        """Strips multi-line <think> blocks."""
        text = "<think>\nline1\nline2\n</think> Result."
        assert strip_think_tags(text) == "Result."

    def test_removes_stray_open_tag(self) -> None:
        """Strips orphaned <think> tag."""
        assert strip_think_tags("<think> partial text") == "partial text"

    def test_removes_stray_close_tag(self) -> None:
        """Strips orphaned </think> tag."""
        assert strip_think_tags("text </think> more") == "text  more"

    def test_no_tags_passthrough(self) -> None:
        """Text without think tags is returned unchanged (stripped)."""
        assert strip_think_tags("RSI is bullish.") == "RSI is bullish."

    def test_empty_string(self) -> None:
        """Empty input returns empty string."""
        assert strip_think_tags("") == ""

    def test_only_think_block_returns_original(self) -> None:
        """String that is entirely a think block returns original (not empty)."""
        result = strip_think_tags("<think>all reasoning</think>")
        assert result == "<think>all reasoning</think>"

    def test_empty_after_strip_returns_original(self) -> None:
        """When stripping would produce empty, falls back to original text."""
        result = strip_think_tags("  <think>only reasoning here</think>  ")
        assert result == "<think>only reasoning here</think>"
        assert len(result) > 0

    def test_multiple_think_blocks(self) -> None:
        """Multiple think blocks are all removed."""
        text = "<think>a</think> X <think>b</think> Y"
        result = strip_think_tags(text)
        assert "<think>" not in result
        assert "X" in result
        assert "Y" in result

    def test_strips_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped from result."""
        assert strip_think_tags("  <think>x</think>  answer  ") == "answer"


# ---------------------------------------------------------------------------
# compute_citation_density
# ---------------------------------------------------------------------------


class TestComputeCitationDensity:
    """Tests for citation density scoring."""

    def test_full_citation(self) -> None:
        """All context labels cited returns 1.0."""
        context = "RSI 14: 62.3\nADX: 28.4\nBB WIDTH: 42.1"
        text = "The RSI 14 is bullish. ADX shows trend. BB WIDTH is moderate."
        assert compute_citation_density(context, text) == pytest.approx(1.0)

    def test_no_citation(self) -> None:
        """No context labels cited returns 0.0."""
        context = "RSI 14: 62.3\nADX: 28.4"
        text = "The stock is going up based on momentum."
        assert compute_citation_density(context, text) == pytest.approx(0.0)

    def test_partial_citation(self) -> None:
        """Some context labels cited returns correct fraction."""
        context = "RSI 14: 62.3\nADX: 28.4\nBB WIDTH: 42.1\nATR PCT: 15.0"
        text = "RSI 14 is bullish. BB WIDTH is narrowing."
        # 2 out of 4 labels cited
        assert compute_citation_density(context, text) == pytest.approx(0.5)

    def test_empty_context_block(self) -> None:
        """Empty context block returns 0.0."""
        assert compute_citation_density("", "some agent text") == pytest.approx(0.0)

    def test_multiple_texts(self) -> None:
        """Multiple text arguments are combined for citation search."""
        context = "RSI 14: 62.3\nADX: 28.4"
        text_a = "RSI 14 is bullish."
        text_b = "ADX shows trend."
        assert compute_citation_density(context, text_a, text_b) == pytest.approx(1.0)
