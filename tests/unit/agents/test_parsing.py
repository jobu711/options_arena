"""Tests for _parsing.py — DebateDeps, DebateResult, render_context_block.

Tests cover:
  - DebateDeps construction with required fields
  - DebateDeps optional fields (opponent_argument, bull_response, bear_response)
  - DebateResult construction
  - DebateResult field access
  - render_context_block output format
  - render_context_block contains expected field labels
  - render_context_block renders all MarketContext fields
"""

from __future__ import annotations

import pytest
from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateDeps, DebateResult, render_context_block
from options_arena.models import (
    AgentResponse,
    MarketContext,
    OptionContract,
    SignalDirection,
    TickerScore,
    TradeThesis,
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
