"""Tests for the debate orchestrator — run_debate (6-agent), build_market_context, helpers.

Tests cover:
  - build_market_context field mapping with full data
  - build_market_context handles None signals with safe defaults
  - build_market_context handles empty contracts list
  - build_market_context maps short_pct_of_float from TickerInfo
  - run_debate connection error -> fallback
  - run_debate timeout -> fallback
  - run_debate generic exception -> fallback
  - run_debate fallback properties (is_fallback, confidence, model_used)
  - run_debate duration_ms is positive
  - run_debate persists to repository when provided
  - run_debate persistence failure does not crash
  - run_debate quality gate (<0.4 fallback, <0.6 warning)
  - _opposite_direction helper tests
  - _extract_top_signals helper tests
  - classify_macd_signal helper tests
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from options_arena.agents._parsing import DebateResult
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.orchestrator import (
    _build_model_settings,
    _extract_top_signals,
    _format_contract_refs,
    _opposite_direction,
    build_market_context,
    classify_macd_signal,
    run_debate,
    should_debate,
)
from options_arena.agents.risk import risk_agent
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    DebateConfig,
    IndicatorSignals,
    LLMProvider,
    MacdSignal,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False

_PIPELINE = "options_arena.agents.orchestrator._run_debate_pipeline"


# ---------------------------------------------------------------------------
# build_market_context
# ---------------------------------------------------------------------------


class TestBuildMarketContext:
    """Tests for build_market_context field mapping."""

    @pytest.mark.smoke
    def test_maps_ticker_from_score(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Ticker comes from TickerScore."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.ticker == "AAPL"

    def test_maps_price_from_quote(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Current price comes from Quote."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.current_price == Decimal("185.50")

    def test_maps_52w_range_from_ticker_info(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """52-week high/low come from TickerInfo."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.price_52w_high == Decimal("199.62")
        assert ctx.price_52w_low == Decimal("164.08")

    def test_maps_rsi_from_signals(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """RSI comes from TickerScore.signals."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.rsi_14 == pytest.approx(62.3)

    def test_maps_sector_from_ticker_info(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Sector comes from TickerInfo."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.sector == "Information Technology"

    def test_maps_dividend_yield_from_ticker_info(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Dividend yield comes from TickerInfo."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.dividend_yield == pytest.approx(0.005)

    def test_maps_delta_from_contract_greeks(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Target delta comes from first contract's Greeks."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.target_delta == pytest.approx(0.35)

    def test_maps_strike_from_contract(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Target strike comes from first contract."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.target_strike == Decimal("190.00")

    def test_maps_max_pain_distance_from_signals(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """max_pain_distance passes through from TickerScore.signals."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(max_pain_distance=3.5),
            scan_run_id=1,
        )
        ctx = build_market_context(score, mock_quote, mock_ticker_info, [mock_option_contract])
        assert ctx.max_pain_distance == pytest.approx(3.5)

    def test_handles_none_signals_with_defaults(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """None indicator values pass through as None (except rsi_14 which has neutral default)."""
        score = TickerScore(
            ticker="AAPL",
            composite_score=50.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),  # all None
            scan_run_id=1,
        )
        ctx = build_market_context(score, mock_quote, mock_ticker_info, [mock_option_contract])
        assert ctx.rsi_14 == pytest.approx(50.0)  # default for None RSI
        assert ctx.iv_rank is None  # None passes through
        assert ctx.iv_percentile is None
        assert ctx.put_call_ratio is None
        assert ctx.max_pain_distance is None

    def test_handles_empty_contracts(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Empty contracts list uses safe defaults for strike, delta, DTE."""
        ctx = build_market_context(mock_ticker_score, mock_quote, mock_ticker_info, [])
        assert ctx.dte_target == 45  # default
        assert ctx.target_strike == mock_quote.price  # falls back to quote price
        assert ctx.target_delta == pytest.approx(0.35)  # default

    def test_exercise_style_always_american(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Exercise style is always AMERICAN for US equity options."""
        from options_arena.models import ExerciseStyle

        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.exercise_style == ExerciseStyle.AMERICAN

    def test_data_timestamp_is_utc(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """data_timestamp is UTC."""
        ctx = build_market_context(
            mock_ticker_score, mock_quote, mock_ticker_info, [mock_option_contract]
        )
        assert ctx.data_timestamp.tzinfo is not None

    def test_short_pct_of_float_mapped(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_option_contract: OptionContract,
    ) -> None:
        """short_pct_of_float is mapped from ticker_info."""
        from options_arena.models import DividendSource

        info = TickerInfo(
            ticker="AAPL",
            company_name="Apple Inc.",
            sector="Information Technology",
            market_cap=2_800_000_000_000,
            dividend_yield=0.005,
            dividend_source=DividendSource.FORWARD,
            current_price=Decimal("185.50"),
            fifty_two_week_high=Decimal("199.62"),
            fifty_two_week_low=Decimal("164.08"),
            short_pct_of_float=0.15,
        )
        ctx = build_market_context(mock_ticker_score, mock_quote, info, [mock_option_contract])
        assert ctx.short_pct_of_float == pytest.approx(0.15)


# ---------------------------------------------------------------------------
# classify_macd_signal
# ---------------------------------------------------------------------------


class TestClassifyMacdSignal:
    """Tests for classify_macd_signal helper (replaces _derive_macd_signal)."""

    def test_positive_value_bullish(self) -> None:
        assert classify_macd_signal(1.5) == MacdSignal.BULLISH_CROSSOVER

    def test_negative_value_bearish(self) -> None:
        assert classify_macd_signal(-2.3) == MacdSignal.BEARISH_CROSSOVER

    def test_zero_neutral(self) -> None:
        assert classify_macd_signal(0.0) == MacdSignal.NEUTRAL

    def test_none_neutral(self) -> None:
        assert classify_macd_signal(None) == MacdSignal.NEUTRAL


# ---------------------------------------------------------------------------
# _opposite_direction
# ---------------------------------------------------------------------------


class TestOppositeDirection:
    """Tests for _opposite_direction helper."""

    def test_bullish_to_bearish(self) -> None:
        assert _opposite_direction(SignalDirection.BULLISH) == SignalDirection.BEARISH

    def test_bearish_to_bullish(self) -> None:
        assert _opposite_direction(SignalDirection.BEARISH) == SignalDirection.BULLISH

    def test_neutral_stays_neutral(self) -> None:
        assert _opposite_direction(SignalDirection.NEUTRAL) == SignalDirection.NEUTRAL


# ---------------------------------------------------------------------------
# _extract_top_signals
# ---------------------------------------------------------------------------


class TestExtractTopSignals:
    """Tests for _extract_top_signals helper."""

    def test_returns_list_of_strings(self, mock_ticker_score: TickerScore) -> None:
        signals = _extract_top_signals(mock_ticker_score)
        assert isinstance(signals, list)
        for item in signals:
            assert isinstance(item, str)

    def test_includes_rsi_when_present(self, mock_ticker_score: TickerScore) -> None:
        signals = _extract_top_signals(mock_ticker_score)
        assert any("RSI" in s for s in signals)

    def test_max_five_items(self, mock_ticker_score: TickerScore) -> None:
        signals = _extract_top_signals(mock_ticker_score)
        assert len(signals) <= 5

    def test_empty_for_all_none_signals(self) -> None:
        score = TickerScore(
            ticker="AAPL",
            composite_score=50.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        signals = _extract_top_signals(score)
        assert signals == []


# ---------------------------------------------------------------------------
# _format_contract_refs
# ---------------------------------------------------------------------------


class TestFormatContractRefs:
    """Tests for _format_contract_refs helper."""

    def test_formats_contract(self, mock_option_contract: OptionContract) -> None:
        refs = _format_contract_refs([mock_option_contract])
        assert len(refs) == 1
        assert "AAPL" in refs[0]
        assert "190" in refs[0]
        assert "CALL" in refs[0]

    def test_empty_for_no_contracts(self) -> None:
        assert _format_contract_refs([]) == []

    def test_max_three_refs(self, mock_option_contract: OptionContract) -> None:
        refs = _format_contract_refs([mock_option_contract] * 5)
        assert len(refs) == 3


# ---------------------------------------------------------------------------
# run_debate — fallback paths
# ---------------------------------------------------------------------------


class TestRunDebateFallback:
    """Tests for run_debate fallback on various errors."""

    @pytest.mark.asyncio
    async def test_fallback_on_connection_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Connection error triggers data-driven fallback."""
        config = DebateConfig(agent_timeout=10.0, max_total_duration=30.0)

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("Connection refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
        )
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_fallback_on_timeout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Timeout triggers data-driven fallback."""
        config = DebateConfig(agent_timeout=0.001, max_total_duration=0.001)

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            await asyncio.sleep(100)

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
        )
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_fallback_on_generic_exception(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Generic exception triggers data-driven fallback."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise RuntimeError("Unexpected failure")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_fallback_confidence_capped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Fallback thesis confidence equals config.fallback_confidence."""
        config = DebateConfig(agent_timeout=10.0, max_total_duration=30.0, fallback_confidence=0.3)

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
        )
        assert result.thesis.confidence == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_fallback_model_used_is_data_driven(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Fallback agent responses use model_used = 'data-driven-fallback'."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.bull_response.model_used == "data-driven-fallback"
        assert result.bear_response.model_used == "data-driven-fallback"

    @pytest.mark.asyncio
    async def test_fallback_duration_positive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Fallback still records duration."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.duration_ms >= 0


# ---------------------------------------------------------------------------
# run_debate — persistence
# ---------------------------------------------------------------------------


class TestRunDebatePersistence:
    """Tests for run_debate persistence behavior."""

    @pytest.mark.asyncio
    async def test_persists_when_repo_provided(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """run_debate calls save_debate on repository when provided."""
        mock_repo = MagicMock()
        mock_repo.save_debate = AsyncMock(return_value=1)

        # Force fallback to avoid real agent calls
        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
            repository=mock_repo,
        )
        mock_repo.save_debate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_persistence_failure_does_not_crash(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """run_debate does not crash when repository.save_debate raises."""
        mock_repo = MagicMock()
        mock_repo.save_debate = AsyncMock(side_effect=RuntimeError("DB error"))

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        # Should not raise
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
            repository=mock_repo,
        )
        assert result.is_fallback is True

    @pytest.mark.asyncio
    async def test_no_persistence_when_repo_is_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """run_debate does not attempt persistence when repository is None."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        # Should not raise — no repo to call save_debate on
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
            repository=None,
        )
        assert result.is_fallback is True


# ---------------------------------------------------------------------------
# Provider-aware timeout and ModelSettings
# ---------------------------------------------------------------------------


class TestGroqModelConfig:
    """Tests for Groq-only model configuration in debate."""

    @pytest.mark.asyncio
    async def test_groq_success_with_test_model(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Groq config produces a valid DebateResult with TestModel."""
        config = DebateConfig(
            api_key="gsk_test_key_for_testing",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            flow_agent.override(model=TestModel()),
            fundamental_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
            )
        assert isinstance(result, DebateResult)
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_persist_uses_config_model_name(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Persistence uses config.model as model_name."""
        mock_repo = MagicMock()
        mock_repo.save_debate = AsyncMock(return_value=1)

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr(_PIPELINE, fake_run_agents)
        config = DebateConfig(
            api_key="gsk_test_key",
            model="llama-3.3-70b-versatile",
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
            repository=mock_repo,
        )
        mock_repo.save_debate.assert_awaited_once()
        call_kwargs = mock_repo.save_debate.call_args
        assert call_kwargs.kwargs["model_name"] == "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# should_debate() pre-screening gate
# ---------------------------------------------------------------------------


class TestShouldDebate:
    """Tests for the should_debate() pure-function pre-screening gate."""

    def test_returns_false_for_neutral_direction(self) -> None:
        """NEUTRAL direction always skips debate, regardless of score."""
        score = TickerScore(
            ticker="X",
            composite_score=80.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        assert should_debate(score, DebateConfig()) is False

    def test_returns_false_for_score_below_threshold(self) -> None:
        """Score below min_debate_score skips debate."""
        score = TickerScore(
            ticker="X",
            composite_score=20.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        config = DebateConfig(min_debate_score=30.0)
        assert should_debate(score, config) is False

    def test_returns_true_for_bullish_above_threshold(self) -> None:
        """BULLISH + score above threshold proceeds to debate."""
        score = TickerScore(
            ticker="X",
            composite_score=50.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        config = DebateConfig(min_debate_score=30.0)
        assert should_debate(score, config) is True

    def test_score_exactly_at_threshold_returns_true(self) -> None:
        """Score exactly at min_debate_score is inclusive (>=, not >)."""
        score = TickerScore(
            ticker="X",
            composite_score=30.0,
            direction=SignalDirection.BEARISH,
            signals=IndicatorSignals(),
        )
        config = DebateConfig(min_debate_score=30.0)
        assert should_debate(score, config) is True

    def test_score_zero_non_neutral_returns_false(self) -> None:
        """Score 0.0 with non-NEUTRAL direction returns False (below default 30)."""
        score = TickerScore(
            ticker="X",
            composite_score=0.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        assert should_debate(score, DebateConfig()) is False


# ---------------------------------------------------------------------------
# run_debate() screening integration
# ---------------------------------------------------------------------------


class TestRunDebateScreening:
    """Tests for pre-screening integration in run_debate()."""

    @pytest.mark.asyncio
    async def test_screening_returns_fallback_for_neutral(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """run_debate returns screening fallback for NEUTRAL ticker."""
        neutral_score = TickerScore(
            ticker="AAPL",
            composite_score=80.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
        )
        result = await run_debate(
            ticker_score=neutral_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=DebateConfig(),
        )
        assert result.is_fallback is True
        assert "Signal too weak" in result.thesis.summary

    @pytest.mark.asyncio
    async def test_screening_fallback_includes_composite_score(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Screening fallback summary includes composite score and direction."""
        weak_score = TickerScore(
            ticker="AAPL",
            composite_score=15.0,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(),
        )
        result = await run_debate(
            ticker_score=weak_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=DebateConfig(min_debate_score=30.0),
        )
        assert result.is_fallback is True
        assert "15.0/100" in result.thesis.summary
        assert "bullish" in result.thesis.summary

    @pytest.mark.asyncio
    async def test_screening_fallback_skips_persistence(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Screened-out tickers return early -- persistence is not called."""
        mock_repo = MagicMock()
        mock_repo.save_debate = AsyncMock(return_value=1)

        neutral_score = TickerScore(
            ticker="AAPL",
            composite_score=80.0,
            direction=SignalDirection.NEUTRAL,
            signals=IndicatorSignals(),
            scan_run_id=1,
        )
        result = await run_debate(
            ticker_score=neutral_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=DebateConfig(),
            repository=mock_repo,
        )
        assert result.is_fallback is True
        mock_repo.save_debate.assert_not_awaited()


# ---------------------------------------------------------------------------
# Quality gate — completeness_ratio checks
# ---------------------------------------------------------------------------


class TestQualityGate:
    """Tests for the MarketContext completeness quality gate in run_debate()."""

    @pytest.mark.asyncio
    async def test_quality_gate_below_40_triggers_fallback(
        self,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Completeness < 40% triggers data-driven fallback without calling agents."""
        # IndicatorSignals with no options-specific signals populated
        # rsi not in completeness check; only atm_iv_30d + 4 Greeks = 5/15 = 33%
        score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(rsi=62.3),
            scan_run_id=1,
        )
        run_agents_mock = AsyncMock()
        monkeypatch.setattr(_PIPELINE, run_agents_mock)
        result = await run_debate(
            ticker_score=score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.is_fallback is True
        run_agents_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_quality_gate_above_40_proceeds(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Completeness >= 40% allows debate to proceed."""
        # mock_ticker_score has adx, sma_alignment, bb_width, atr_pct,
        # relative_volume (5 in check) + atm_iv_30d from contract + 4 Greeks
        # -> 10/15 = ~67%  which is >= 40%
        with (
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            flow_agent.override(model=TestModel()),
            fundamental_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_quality_gate_between_40_60_logs_warning(
        self,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Completeness between 40% and 60% logs a caution warning but proceeds."""
        import logging

        # Build a score with 7 of 15 fields populated = ~47%
        # (2 indicators + atm_iv_30d from contract + 4 Greeks = 7/15)
        score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(
                rsi=62.3,
                adx=28.4,
                sma_alignment=0.7,
            ),
            scan_run_id=1,
        )
        with (
            caplog.at_level(logging.WARNING, logger="options_arena.agents.orchestrator"),
            trend_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            flow_agent.override(model=TestModel()),
            fundamental_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
            contrarian_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        # Should proceed (not fallback) but log a warning
        assert result.is_fallback is False
        assert any("proceeding with caution" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# _build_model_settings — conditional ModelSettings for extended thinking
# ---------------------------------------------------------------------------


class TestBuildModelSettings:
    """Tests for _build_model_settings helper — provider-aware ModelSettings."""

    def test_groq_standard_settings(self) -> None:
        """Groq provider returns plain ModelSettings with configured temperature."""
        config = DebateConfig(provider=LLMProvider.GROQ, temperature=0.3)
        settings = _build_model_settings(config)
        assert settings["temperature"] == pytest.approx(0.3)
        assert "anthropic_thinking" not in settings

    def test_anthropic_no_thinking(self) -> None:
        """Anthropic without extended thinking returns plain ModelSettings."""
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            enable_extended_thinking=False,
            temperature=0.5,
        )
        settings = _build_model_settings(config)
        assert settings["temperature"] == pytest.approx(0.5)
        assert "anthropic_thinking" not in settings

    def test_anthropic_with_thinking(self) -> None:
        """Anthropic with extended thinking returns AnthropicModelSettings with thinking dict."""
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            enable_extended_thinking=True,
            thinking_budget_tokens=5000,
        )
        settings = _build_model_settings(config)
        assert settings["temperature"] == pytest.approx(1.0)
        assert settings["anthropic_thinking"] == {
            "type": "enabled",
            "budget_tokens": 5000,
        }

    def test_thinking_budget_passed_through(self) -> None:
        """Custom thinking_budget_tokens value is passed through to settings."""
        config = DebateConfig(
            provider=LLMProvider.ANTHROPIC,
            enable_extended_thinking=True,
            thinking_budget_tokens=10000,
        )
        settings = _build_model_settings(config)
        assert "anthropic_thinking" in settings
        assert settings["anthropic_thinking"]["budget_tokens"] == 10000

    def test_groq_ignores_extended_thinking(self) -> None:
        """Groq provider ignores enable_extended_thinking — returns plain settings."""
        config = DebateConfig(
            provider=LLMProvider.GROQ,
            enable_extended_thinking=True,
            temperature=0.4,
        )
        settings = _build_model_settings(config)
        assert settings["temperature"] == pytest.approx(0.4)
        assert "anthropic_thinking" not in settings


# ---------------------------------------------------------------------------
# Financial Datasets integration
# ---------------------------------------------------------------------------


class TestBuildMarketContextFD:
    """Tests for build_market_context with Financial Datasets package."""

    def test_fd_fields_populated_from_package(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Verify fd_* fields populated from FD package components."""
        from datetime import UTC, datetime

        from options_arena.models.financial_datasets import (
            BalanceSheetData,
            FinancialDatasetsPackage,
            FinancialMetricsData,
            IncomeStatementData,
        )

        fd = FinancialDatasetsPackage(
            ticker="AAPL",
            metrics=FinancialMetricsData(
                pe_ratio=28.5,
                revenue_growth=0.08,
                earnings_growth=0.12,
                current_ratio=1.2,
                enterprise_value_to_ebitda=22.0,
                free_cash_flow_yield=0.035,
                profit_margin=0.25,
                gross_margin=0.44,
                operating_margin=0.30,
                net_margin=0.24,
                eps_diluted=6.50,
            ),
            income=IncomeStatementData(
                revenue=383_000_000_000.0,
                net_income=97_000_000_000.0,
                gross_profit=170_000_000_000.0,
                operating_income=115_000_000_000.0,
                eps_diluted=6.42,
                gross_margin=0.45,
                operating_margin=0.31,
                net_margin=0.25,
            ),
            balance_sheet=BalanceSheetData(
                total_debt=111_000_000_000.0,
                total_cash=62_000_000_000.0,
                total_assets=352_000_000_000.0,
            ),
            fetched_at=datetime.now(UTC),
        )

        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
            fd_package=fd,
        )

        # Check fd_* fields from income statement (income takes priority over metrics)
        assert ctx.fd_revenue == pytest.approx(383_000_000_000.0)
        assert ctx.fd_net_income == pytest.approx(97_000_000_000.0)
        assert ctx.fd_gross_profit == pytest.approx(170_000_000_000.0)
        assert ctx.fd_operating_income == pytest.approx(115_000_000_000.0)
        assert ctx.fd_eps_diluted == pytest.approx(6.42)  # income takes priority
        assert ctx.fd_gross_margin == pytest.approx(0.45)  # income takes priority
        assert ctx.fd_operating_margin == pytest.approx(0.31)  # income takes priority
        assert ctx.fd_net_margin == pytest.approx(0.25)  # income takes priority

        # Check fd_* fields from balance sheet
        assert ctx.fd_total_debt == pytest.approx(111_000_000_000.0)
        assert ctx.fd_total_cash == pytest.approx(62_000_000_000.0)
        assert ctx.fd_total_assets == pytest.approx(352_000_000_000.0)

        # Check fd_* fields from metrics
        assert ctx.fd_current_ratio == pytest.approx(1.2)
        assert ctx.fd_revenue_growth == pytest.approx(0.08)
        assert ctx.fd_earnings_growth == pytest.approx(0.12)
        assert ctx.fd_ev_to_ebitda == pytest.approx(22.0)
        assert ctx.fd_free_cash_flow_yield == pytest.approx(0.035)

    def test_fd_none_fallback(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Verify all fd_* fields remain None when fd_package is None."""
        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
            fd_package=None,
        )

        assert ctx.fd_revenue is None
        assert ctx.fd_net_income is None
        assert ctx.fd_gross_profit is None
        assert ctx.fd_operating_income is None
        assert ctx.fd_eps_diluted is None
        assert ctx.fd_gross_margin is None
        assert ctx.fd_operating_margin is None
        assert ctx.fd_net_margin is None
        assert ctx.fd_total_debt is None
        assert ctx.fd_total_cash is None
        assert ctx.fd_total_assets is None
        assert ctx.fd_current_ratio is None
        assert ctx.fd_revenue_growth is None
        assert ctx.fd_earnings_growth is None
        assert ctx.fd_ev_to_ebitda is None
        assert ctx.fd_free_cash_flow_yield is None

    def test_fd_priority_over_openbb(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Verify FD value takes priority when both FD and OpenBB provide pe_ratio."""
        from datetime import UTC, datetime

        from options_arena.models.financial_datasets import (
            FinancialDatasetsPackage,
            FinancialMetricsData,
        )
        from options_arena.models.openbb import FundamentalSnapshot

        fd = FinancialDatasetsPackage(
            ticker="AAPL",
            metrics=FinancialMetricsData(
                pe_ratio=28.5,
                forward_pe=25.0,
                peg_ratio=1.5,
                price_to_book=40.0,
                debt_to_equity=1.8,
                revenue_growth=0.08,
                profit_margin=0.25,
            ),
            fetched_at=datetime.now(UTC),
        )

        openbb_fundamentals = FundamentalSnapshot(
            ticker="AAPL",
            pe_ratio=30.0,
            forward_pe=27.0,
            peg_ratio=2.0,
            price_to_book=45.0,
            debt_to_equity=2.1,
            revenue_growth=0.06,
            profit_margin=0.22,
            fetched_at=datetime.now(UTC),
        )

        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
            fundamentals=openbb_fundamentals,
            fd_package=fd,
        )

        # FD values take priority
        assert ctx.pe_ratio == pytest.approx(28.5)
        assert ctx.forward_pe == pytest.approx(25.0)
        assert ctx.peg_ratio == pytest.approx(1.5)
        assert ctx.price_to_book == pytest.approx(40.0)
        assert ctx.debt_to_equity == pytest.approx(1.8)
        assert ctx.revenue_growth == pytest.approx(0.08)
        assert ctx.profit_margin == pytest.approx(0.25)

    def test_openbb_fallback_when_fd_none(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Verify OpenBB value used when FD field is None."""
        from datetime import UTC, datetime

        from options_arena.models.financial_datasets import (
            FinancialDatasetsPackage,
            FinancialMetricsData,
        )
        from options_arena.models.openbb import FundamentalSnapshot

        # FD has pe_ratio but not forward_pe
        fd = FinancialDatasetsPackage(
            ticker="AAPL",
            metrics=FinancialMetricsData(
                pe_ratio=28.5,
                forward_pe=None,
            ),
            fetched_at=datetime.now(UTC),
        )

        openbb_fundamentals = FundamentalSnapshot(
            ticker="AAPL",
            pe_ratio=30.0,
            forward_pe=27.0,
            fetched_at=datetime.now(UTC),
        )

        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
            fundamentals=openbb_fundamentals,
            fd_package=fd,
        )

        # FD wins for pe_ratio
        assert ctx.pe_ratio == pytest.approx(28.5)
        # OpenBB fallback for forward_pe
        assert ctx.forward_pe == pytest.approx(27.0)

    def test_fd_partial_package(
        self,
        mock_ticker_score: TickerScore,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Verify partial FD package (metrics only, no income/balance_sheet)."""
        from datetime import UTC, datetime

        from options_arena.models.financial_datasets import (
            FinancialDatasetsPackage,
            FinancialMetricsData,
        )

        fd = FinancialDatasetsPackage(
            ticker="AAPL",
            metrics=FinancialMetricsData(current_ratio=1.5),
            income=None,
            balance_sheet=None,
            fetched_at=datetime.now(UTC),
        )

        ctx = build_market_context(
            mock_ticker_score,
            mock_quote,
            mock_ticker_info,
            [mock_option_contract],
            fd_package=fd,
        )

        # Metrics field populated
        assert ctx.fd_current_ratio == pytest.approx(1.5)
        # Income fields remain None
        assert ctx.fd_revenue is None
        assert ctx.fd_net_income is None
        # Balance sheet fields remain None
        assert ctx.fd_total_debt is None
        assert ctx.fd_total_cash is None
