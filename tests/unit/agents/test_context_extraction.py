"""Tests for the _context.py extraction — verify function behavior and backward compat.

Tests cover:
  - should_recommend returns False for NEUTRAL direction
  - build_market_context returns a valid MarketContext model
  - classify_macd_signal classifies positive MACD as BULLISH_CROSSOVER
  - classify_macd_signal classifies negative MACD as BEARISH_CROSSOVER
  - backward-compat imports from orchestrator still work after extraction
"""

from __future__ import annotations

import pytest
from pydantic_ai import models

from options_arena.agents._context import (
    _build_model_settings,
    build_market_context,
    classify_macd_signal,
    should_recommend,
)
from options_arena.models import (
    DebateConfig,
    LLMProvider,
    MacdSignal,
    MarketContext,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)
from tests.factories import (
    make_ticker_score,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# should_recommend
# ---------------------------------------------------------------------------


class TestShouldRecommend:
    """Verify should_recommend gating logic."""

    def test_should_recommend_neutral_returns_false(self) -> None:
        """NEUTRAL direction always returns False regardless of score."""
        config = DebateConfig()
        score = make_ticker_score(composite_score=99.0, direction=SignalDirection.NEUTRAL)
        assert should_recommend(score, config) is False

    def test_should_recommend_at_threshold_returns_true(self) -> None:
        """Score exactly at min_recommendation_score returns True."""
        config = DebateConfig(min_recommendation_score=50.0)
        score = make_ticker_score(composite_score=50.0, direction=SignalDirection.BULLISH)
        assert should_recommend(score, config) is True

    def test_should_recommend_below_threshold_returns_false(self) -> None:
        """Score below min_recommendation_score returns False."""
        config = DebateConfig(min_recommendation_score=50.0)
        score = make_ticker_score(composite_score=49.9, direction=SignalDirection.BULLISH)
        assert should_recommend(score, config) is False


# ---------------------------------------------------------------------------
# classify_macd_signal
# ---------------------------------------------------------------------------


class TestClassifyMacdSignal:
    """Verify MACD signal classification."""

    def test_classify_macd_signal_bullish(self) -> None:
        """Positive centered MACD classifies as BULLISH_CROSSOVER."""
        assert classify_macd_signal(5.0) == MacdSignal.BULLISH_CROSSOVER

    def test_classify_macd_signal_bearish(self) -> None:
        """Negative centered MACD classifies as BEARISH_CROSSOVER."""
        assert classify_macd_signal(-3.0) == MacdSignal.BEARISH_CROSSOVER

    def test_classify_macd_signal_none(self) -> None:
        """None MACD classifies as NEUTRAL."""
        assert classify_macd_signal(None) == MacdSignal.NEUTRAL

    def test_classify_macd_signal_zero(self) -> None:
        """Zero MACD classifies as NEUTRAL."""
        assert classify_macd_signal(0.0) == MacdSignal.NEUTRAL

    def test_classify_macd_signal_nan(self) -> None:
        """NaN MACD classifies as NEUTRAL."""
        assert classify_macd_signal(float("nan")) == MacdSignal.NEUTRAL

    def test_classify_macd_signal_inf(self) -> None:
        """Inf MACD classifies as NEUTRAL."""
        assert classify_macd_signal(float("inf")) == MacdSignal.NEUTRAL


# ---------------------------------------------------------------------------
# build_market_context
# ---------------------------------------------------------------------------


class TestBuildMarketContext:
    """Verify build_market_context produces a valid MarketContext."""

    def test_build_market_context_returns_valid_model(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """build_market_context returns a properly typed MarketContext."""
        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
        )
        assert isinstance(ctx, MarketContext)
        assert ctx.ticker == "AAPL"
        assert ctx.current_price == mock_quote.price
        assert ctx.sector == "Information Technology"

    def test_build_market_context_empty_contracts(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Empty contracts list uses safe defaults."""
        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [],
        )
        assert isinstance(ctx, MarketContext)
        assert ctx.dte_target == 45
        assert ctx.target_delta == pytest.approx(0.35)
        assert ctx.target_gamma is None
        assert ctx.contract_mid is None


# ---------------------------------------------------------------------------
# _build_model_settings
# ---------------------------------------------------------------------------


class TestBuildModelSettings:
    """Verify provider-appropriate ModelSettings construction."""

    def test_groq_returns_standard_settings(self) -> None:
        """Groq provider returns standard ModelSettings."""
        config = DebateConfig(temperature=0.3)
        settings = _build_model_settings(config)
        assert settings.get("temperature") == pytest.approx(0.3)

    def test_anthropic_with_thinking_returns_anthropic_settings(self) -> None:
        """Anthropic with extended thinking forces temperature=1.0."""
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            enable_extended_thinking=True,
            thinking_budget_tokens=4096,
        )
        settings = _build_model_settings(config)
        assert settings.get("temperature") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Verify imports from _context work after orchestrator deletion."""

    def test_import_from_context_module(self) -> None:
        """Importing from _context works for relocated functions."""
        from options_arena.agents._context import (
            _build_model_settings as ctx_build_settings,
        )
        from options_arena.agents._context import (
            build_market_context as ctx_build_ctx,
        )
        from options_arena.agents._context import (
            classify_macd_signal as ctx_classify,
        )

        # Verify they're the same functions (identity check)
        assert ctx_build_ctx is build_market_context
        assert ctx_classify is classify_macd_signal
        assert ctx_build_settings is _build_model_settings

    def test_should_recommend_in_package_init(self) -> None:
        """should_recommend is importable from agents package."""
        from options_arena.agents import should_recommend as pkg_should_recommend

        assert pkg_should_recommend is should_recommend
