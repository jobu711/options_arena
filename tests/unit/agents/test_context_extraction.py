"""Tests for the _context.py extraction — verify function behavior and backward compat.

Tests cover:
  - should_recommend is a pure alias for should_debate
  - should_recommend returns False for NEUTRAL direction
  - build_market_context returns a valid MarketContext model
  - classify_macd_signal classifies positive MACD as BULLISH_CROSSOVER
  - classify_macd_signal classifies negative MACD as BEARISH_CROSSOVER
  - extract_agent_predictions builds correct AgentPrediction list
  - backward-compat imports from orchestrator still work after extraction
"""

from __future__ import annotations

import pytest
from pydantic_ai import models

from options_arena.agents._context import (
    _build_model_settings,
    build_market_context,
    classify_macd_signal,
    extract_agent_predictions,
    should_debate,
    should_recommend,
)
from options_arena.models import (
    ContrarianThesis,
    DebateConfig,
    FlowThesis,
    LLMProvider,
    MacdSignal,
    MarketContext,
    OptionContract,
    Quote,
    RiskAssessment,
    RiskLevel,
    SignalDirection,
    TickerInfo,
    TickerScore,
    VolAssessment,
    VolatilityThesis,
)
from tests.factories import (
    make_debate_result,
    make_ticker_score,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# should_recommend / should_debate
# ---------------------------------------------------------------------------


class TestShouldRecommend:
    """Verify should_recommend is a pure alias for should_debate."""

    def test_should_recommend_matches_should_debate(self) -> None:
        """should_recommend returns the same result as should_debate for bullish."""
        config = DebateConfig()
        score = make_ticker_score(composite_score=72.5, direction=SignalDirection.BULLISH)
        assert should_recommend(score, config) == should_debate(score, config)

    def test_should_recommend_matches_should_debate_low_score(self) -> None:
        """should_recommend returns the same result as should_debate for low score."""
        config = DebateConfig()
        score = make_ticker_score(composite_score=30.0, direction=SignalDirection.BEARISH)
        assert should_recommend(score, config) == should_debate(score, config)

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
# extract_agent_predictions
# ---------------------------------------------------------------------------


class TestExtractAgentPredictions:
    """Verify extraction produces correct AgentPrediction list."""

    def test_extract_agent_predictions_from_debate_result(self) -> None:
        """Extract predictions from a DebateResult with flow and vol responses."""
        flow = FlowThesis(
            direction=SignalDirection.BULLISH,
            confidence=0.80,
            gex_interpretation="positive gamma exposure",
            smart_money_signal="accumulation",
            oi_analysis="rising OI with calls",
            volume_confirmation="above average",
            key_flow_factors=["high call volume"],
            model_used="test",
        )
        vol = VolatilityThesis(
            iv_assessment=VolAssessment.UNDERPRICED,
            iv_rank_interpretation="IV in low range",
            confidence=0.70,
            strategy_rationale="buy premium",
            suggested_strikes=["190C"],
            key_vol_factors=["low IV rank"],
            model_used="test",
            direction=SignalDirection.BULLISH,
        )
        result = make_debate_result(flow_response=flow, vol_response=vol)
        predictions = extract_agent_predictions(debate_id=42, result=result)

        # Should have trend (from bull_response), flow, and volatility
        agent_names = [p.agent_name for p in predictions]
        assert "trend" in agent_names
        assert "flow" in agent_names
        assert "volatility" in agent_names

        # Check flow prediction details
        flow_pred = next(p for p in predictions if p.agent_name == "flow")
        assert flow_pred.direction == SignalDirection.BULLISH
        assert flow_pred.confidence == pytest.approx(0.80)
        assert flow_pred.debate_id == 42

    def test_extract_agent_predictions_all_none(self) -> None:
        """All-None responses still produces trend prediction from bull_response."""
        result = make_debate_result()
        predictions = extract_agent_predictions(debate_id=1, result=result)
        # bull_response is always set in make_debate_result -> trend prediction
        assert len(predictions) >= 1
        assert predictions[0].agent_name == "trend"

    def test_extract_agent_predictions_with_contrarian(self) -> None:
        """Contrarian uses dissent_direction and dissent_confidence."""
        contrarian = ContrarianThesis(
            dissent_direction=SignalDirection.BEARISH,
            dissent_confidence=0.65,
            primary_challenge="momentum exhaustion",
            overlooked_risks=["sector rotation"],
            consensus_weakness="narrow breadth",
            alternative_scenario="pullback to support",
            model_used="test",
        )
        result = make_debate_result(contrarian_response=contrarian)
        predictions = extract_agent_predictions(debate_id=10, result=result)

        contrarian_pred = next(p for p in predictions if p.agent_name == "contrarian")
        assert contrarian_pred.direction == SignalDirection.BEARISH
        assert contrarian_pred.confidence == pytest.approx(0.65)

    def test_extract_agent_predictions_with_risk(self) -> None:
        """Risk agent has no direction field."""
        risk = RiskAssessment(
            risk_level=RiskLevel.MODERATE,
            confidence=0.55,
            max_loss_estimate="$500",
            key_risks=["earnings risk"],
            risk_mitigants=["spread collar"],
            model_used="test",
        )
        result = make_debate_result(risk_response=risk)
        predictions = extract_agent_predictions(debate_id=5, result=result)

        risk_pred = next(p for p in predictions if p.agent_name == "risk")
        assert risk_pred.direction is None
        assert risk_pred.confidence == pytest.approx(0.55)


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
        from options_arena.agents._context import (
            extract_agent_predictions as ctx_extract,
        )
        from options_arena.agents._context import (
            should_debate as ctx_should_debate,
        )

        # Verify they're the same functions (identity check)
        assert ctx_should_debate is should_debate
        assert ctx_build_ctx is build_market_context
        assert ctx_classify is classify_macd_signal
        assert ctx_extract is extract_agent_predictions
        assert ctx_build_settings is _build_model_settings

    def test_should_recommend_in_package_init(self) -> None:
        """should_recommend is importable from agents package."""
        from options_arena.agents import should_recommend as pkg_should_recommend

        assert pkg_should_recommend is should_recommend
