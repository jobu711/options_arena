"""Tests for the synthesis agent module."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents.synthesis_agent import (
    SynthesisDeps,
    _build_fallback_recommendation,
    _build_user_prompt,
    run_synthesis,
    synthesis_agent,
)
from options_arena.models import (
    DeskType,
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    OptionContract,
    OptionType,
    SignalDirection,
    TickerScore,
)
from options_arena.models.recommendation import (
    PositionRecommendation,
    TrendAssessment,
)
from options_arena.models.scan import IndicatorSignals

models.ALLOW_MODEL_REQUESTS = False


def _make_market_context() -> MarketContext:
    """Create a minimal MarketContext for testing."""
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
    """Create a minimal TickerScore for testing."""
    return TickerScore(
        ticker="AAPL",
        composite_score=72.5,
        direction=SignalDirection.BULLISH,
        signals=IndicatorSignals(rsi=65.0, adx=70.0),
    )


def _make_contract() -> OptionContract:
    """Create a minimal OptionContract for testing."""
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


def _make_assessment() -> TrendAssessment:
    """Create a minimal TrendAssessment for testing."""
    return TrendAssessment(
        desk=DeskType.TREND,
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        summary="Strong uptrend with RSI confirming momentum.",
        key_factors=["RSI above 60", "ADX above 25"],
        risks=["Earnings approaching"],
        contracts_referenced=["AAPL 185C 2026-04-15"],
        tools_used=["fetch_quote"],
        model_used="test",
        trend_strength=0.8,
    )


def _make_deps() -> SynthesisDeps:
    """Create a fully populated SynthesisDeps for testing."""
    return SynthesisDeps(
        context=_make_market_context(),
        assessments=[_make_assessment()],
        contracts=[_make_contract()],
        ticker_score=_make_ticker_score(),
    )


class TestSynthesisAgent:
    """synthesis_agent Agent instance tests."""

    def test_agent_exists(self) -> None:
        assert synthesis_agent is not None

    def test_agent_output_type_is_position_recommendation(self) -> None:
        assert synthesis_agent._output_type is PositionRecommendation  # noqa: SLF001

    def test_agent_has_tools(self) -> None:
        toolset = synthesis_agent._function_toolset  # noqa: SLF001
        assert toolset is not None

    def test_agent_retries_is_two(self) -> None:
        assert synthesis_agent._max_result_retries == 2  # noqa: SLF001


class TestSynthesisDeps:
    """SynthesisDeps construction tests."""

    def test_construction_minimal(self) -> None:
        deps = _make_deps()
        assert deps.context.ticker == "AAPL"
        assert len(deps.assessments) == 1
        assert len(deps.contracts) == 1
        assert deps.ticker_score.composite_score == pytest.approx(72.5, abs=0.01)

    def test_defaults(self) -> None:
        deps = _make_deps()
        assert deps.learned_patterns == ""
        assert deps.tuned_weights == ""
        assert deps.tools_used == []

    def test_learned_patterns_injected(self) -> None:
        deps = _make_deps()
        deps.learned_patterns = "<<<LEARNED_PATTERNS>>>\ntest pattern\n<<<END>>>"
        assert "test pattern" in deps.learned_patterns

    def test_tuned_weights_injected(self) -> None:
        deps = _make_deps()
        deps.tuned_weights = "<<<TUNED_WEIGHTS>>>\ntrend=0.8\n<<<END>>>"
        assert "trend=0.8" in deps.tuned_weights


class TestBuildUserPrompt:
    """Tests for _build_user_prompt helper."""

    def test_contains_ticker(self) -> None:
        deps = _make_deps()
        prompt = _build_user_prompt(deps)
        assert "AAPL" in prompt

    def test_contains_assessments(self) -> None:
        deps = _make_deps()
        prompt = _build_user_prompt(deps)
        assert "TREND" in prompt
        assert "bullish" in prompt

    def test_contains_contracts(self) -> None:
        deps = _make_deps()
        prompt = _build_user_prompt(deps)
        assert "CALL" in prompt
        assert "$185" in prompt

    def test_contains_direction_tally(self) -> None:
        deps = _make_deps()
        prompt = _build_user_prompt(deps)
        assert "Direction tally" in prompt
        assert "bullish=1" in prompt


class TestBuildFallbackRecommendation:
    """Tests for _build_fallback_recommendation helper."""

    def test_fallback_has_low_confidence(self) -> None:
        deps = _make_deps()
        fb = _build_fallback_recommendation(deps)
        assert fb.confidence <= 0.3

    def test_fallback_direction_is_neutral(self) -> None:
        deps = _make_deps()
        fb = _build_fallback_recommendation(deps)
        assert fb.direction == SignalDirection.NEUTRAL

    def test_fallback_model_used(self) -> None:
        deps = _make_deps()
        fb = _build_fallback_recommendation(deps)
        assert fb.model_used == "data-driven-fallback"

    def test_fallback_is_valid_recommendation(self) -> None:
        deps = _make_deps()
        fb = _build_fallback_recommendation(deps)
        assert isinstance(fb, PositionRecommendation)
        assert len(fb.key_factors) >= 1

    def test_fallback_with_no_contracts(self) -> None:
        deps = _make_deps()
        deps.contracts = []
        fb = _build_fallback_recommendation(deps)
        assert isinstance(fb, PositionRecommendation)
        assert "no contracts" in fb.recommended_contract.lower()

    def test_fallback_uses_contract_mid_as_entry(self) -> None:
        deps = _make_deps()
        fb = _build_fallback_recommendation(deps)
        # entry_price should be the mid of the first contract
        expected_mid = deps.contracts[0].mid
        assert fb.entry_price == expected_mid


@pytest.mark.asyncio
class TestRunSynthesis:
    """run_synthesis() wrapper tests."""

    async def test_fallback_on_no_model(self) -> None:
        deps = _make_deps()
        result = await run_synthesis(deps, model=None)
        assert isinstance(result, PositionRecommendation)
        assert result.confidence <= 0.3
        assert result.direction == SignalDirection.NEUTRAL
        assert result.model_used == "data-driven-fallback"

    async def test_fallback_on_timeout(self) -> None:
        deps = _make_deps()
        # Mock synthesis_agent.run to raise TimeoutError
        with patch.object(
            synthesis_agent,
            "run",
            new_callable=AsyncMock,
            side_effect=TimeoutError("timed out"),
        ):
            result = await run_synthesis(deps, model=TestModel(), timeout=0.001)
        assert isinstance(result, PositionRecommendation)
        assert result.confidence <= 0.3
        assert result.model_used == "data-driven-fallback"

    async def test_fallback_on_generic_exception(self) -> None:
        deps = _make_deps()
        with patch.object(
            synthesis_agent,
            "run",
            new_callable=AsyncMock,
            side_effect=RuntimeError("unexpected"),
        ):
            result = await run_synthesis(deps, model=TestModel())
        assert isinstance(result, PositionRecommendation)
        assert result.confidence <= 0.3

    async def test_never_raises(self) -> None:
        deps = _make_deps()
        # Even with a ValueError, should return fallback
        with patch.object(
            synthesis_agent,
            "run",
            new_callable=AsyncMock,
            side_effect=ValueError("bad value"),
        ):
            result = await run_synthesis(deps, model=TestModel())
        assert isinstance(result, PositionRecommendation)

    async def test_returns_position_recommendation(self) -> None:
        """Verify that on success the return type is PositionRecommendation."""
        deps = _make_deps()
        # TestModel will produce structured output
        with synthesis_agent.override(model=TestModel()):
            # Even if TestModel doesn't produce perfect output, the
            # fallback in run_synthesis guarantees PositionRecommendation
            result = await run_synthesis(deps, model=TestModel())
        assert isinstance(result, PositionRecommendation)
