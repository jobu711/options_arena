"""Tests for the debate orchestrator — run_debate, build_market_context, helpers.

Tests cover:
  - build_market_context field mapping with full data
  - build_market_context handles None signals with safe defaults
  - build_market_context handles empty contracts list
  - run_debate success path with TestModel overrides
  - run_debate connection error -> fallback
  - run_debate timeout -> fallback
  - run_debate generic exception -> fallback
  - run_debate fallback properties (is_fallback, confidence, model_used)
  - run_debate duration_ms is positive
  - run_debate persists to repository when provided
  - run_debate persistence failure does not crash
  - _opposite_direction helper tests
  - _extract_top_signals helper tests
  - _derive_macd_signal helper tests
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
from options_arena.agents.bear import bear_agent
from options_arena.agents.bull import bull_agent
from options_arena.agents.orchestrator import (
    DebatePhase,
    _derive_macd_signal,
    _extract_top_signals,
    _format_contract_refs,
    _opposite_direction,
    build_market_context,
    run_debate,
    should_debate,
)
from options_arena.agents.risk import risk_agent
from options_arena.agents.volatility import volatility_agent
from options_arena.models import (
    AgentResponse,
    DebateConfig,
    IndicatorSignals,
    MacdSignal,
    OptionContract,
    Quote,
    SignalDirection,
    TickerInfo,
    TickerScore,
    TradeThesis,
    VolatilityThesis,
)

# Prevent accidental real API calls
models.ALLOW_MODEL_REQUESTS = False


# ---------------------------------------------------------------------------
# build_market_context
# ---------------------------------------------------------------------------


class TestBuildMarketContext:
    """Tests for build_market_context field mapping."""

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


# ---------------------------------------------------------------------------
# _derive_macd_signal
# ---------------------------------------------------------------------------


class TestDeriveMacdSignal:
    """Tests for _derive_macd_signal helper."""

    def test_bullish_direction(self) -> None:
        assert _derive_macd_signal(SignalDirection.BULLISH) == MacdSignal.BULLISH_CROSSOVER

    def test_bearish_direction(self) -> None:
        assert _derive_macd_signal(SignalDirection.BEARISH) == MacdSignal.BEARISH_CROSSOVER

    def test_neutral_direction(self) -> None:
        assert _derive_macd_signal(SignalDirection.NEUTRAL) == MacdSignal.NEUTRAL


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
# run_debate — success path
# ---------------------------------------------------------------------------


class TestRunDebateSuccess:
    """Tests for run_debate success path using TestModel."""

    @pytest.mark.asyncio
    async def test_returns_debate_result(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """run_debate returns a DebateResult on success."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert isinstance(result, DebateResult)

    @pytest.mark.asyncio
    async def test_not_fallback(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Successful run sets is_fallback to False."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
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
    async def test_bull_response_is_agent_response(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Bull response is AgentResponse."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert isinstance(result.bull_response, AgentResponse)

    @pytest.mark.asyncio
    async def test_bear_response_is_agent_response(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Bear response is AgentResponse."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert isinstance(result.bear_response, AgentResponse)

    @pytest.mark.asyncio
    async def test_thesis_is_trade_thesis(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Thesis is a TradeThesis."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert isinstance(result.thesis, TradeThesis)

    @pytest.mark.asyncio
    async def test_duration_ms_positive(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Duration is non-negative."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert result.duration_ms >= 0


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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
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

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
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
    async def test_screening_fallback_persists_when_repository_provided(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Screened-out tickers are still persisted when a repository is provided."""
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
        mock_repo.save_debate.assert_awaited_once()


# ---------------------------------------------------------------------------
# Volatility agent integration — orchestrator behavior with vol enabled/disabled
# ---------------------------------------------------------------------------


class TestVolatilityAgentIntegration:
    """Tests for volatility agent integration in run_debate()."""

    @pytest.mark.asyncio
    async def test_vol_enabled_produces_vol_response(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """When enable_volatility_agent=True, result.vol_response is not None."""
        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
            enable_volatility_agent=True,
        )
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
            )
        assert result.is_fallback is False
        assert isinstance(result.vol_response, VolatilityThesis)

    @pytest.mark.asyncio
    async def test_vol_disabled_skips_vol_agent(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """When enable_volatility_agent=False (default), vol_response is None."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert result.is_fallback is False
        assert result.vol_response is None

    @pytest.mark.asyncio
    async def test_vol_agent_failure_triggers_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Volatility agent failure triggers the never-raises fallback pattern."""
        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
            enable_volatility_agent=True,
        )

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise RuntimeError("Volatility agent exploded")

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=config,
        )
        assert result.is_fallback is True
        assert result.vol_response is None

    @pytest.mark.asyncio
    async def test_fallback_result_has_vol_response_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Fallback results always have vol_response=None."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.is_fallback is True
        assert result.vol_response is None

    @pytest.mark.asyncio
    async def test_screening_fallback_has_vol_response_none(
        self,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_option_contract: OptionContract,
    ) -> None:
        """Screening fallback for neutral ticker has vol_response=None."""
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
        assert result.vol_response is None


# ---------------------------------------------------------------------------
# Bull rebuttal integration — orchestrator behavior with rebuttal enabled/disabled
# ---------------------------------------------------------------------------


class TestBullRebuttalIntegration:
    """Tests for bull rebuttal integration in run_debate()."""

    @pytest.mark.asyncio
    async def test_rebuttal_enabled_produces_bull_rebuttal(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """When enable_rebuttal=True, result.bull_rebuttal is not None."""
        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
            enable_rebuttal=True,
        )
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
            )
        assert result.is_fallback is False
        assert isinstance(result.bull_rebuttal, AgentResponse)

    @pytest.mark.asyncio
    async def test_rebuttal_disabled_skips_rebuttal(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """When enable_rebuttal=False (default), bull_rebuttal is None."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
            )
        assert result.is_fallback is False
        assert result.bull_rebuttal is None

    @pytest.mark.asyncio
    async def test_fallback_result_has_bull_rebuttal_none(
        self,
        monkeypatch: pytest.MonkeyPatch,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Fallback results always have bull_rebuttal=None."""

        async def fake_run_agents(*args: object, **kwargs: object) -> None:
            raise httpx.ConnectError("refused")

        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", fake_run_agents)
        result = await run_debate(
            ticker_score=mock_ticker_score,
            contracts=[mock_option_contract],
            quote=mock_quote,
            ticker_info=mock_ticker_info,
            config=mock_debate_config,
        )
        assert result.is_fallback is True
        assert result.bull_rebuttal is None

    @pytest.mark.asyncio
    async def test_rebuttal_and_volatility_both_enabled(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """When both enable_rebuttal and enable_volatility_agent are True, both are populated."""
        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
            enable_rebuttal=True,
            enable_volatility_agent=True,
        )
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            volatility_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
            )
        assert result.is_fallback is False
        assert isinstance(result.bull_rebuttal, AgentResponse)
        assert isinstance(result.vol_response, VolatilityThesis)


# ---------------------------------------------------------------------------
# Quality gate — completeness_ratio checks
# ---------------------------------------------------------------------------


class TestQualityGate:
    """Tests for the MarketContext completeness quality gate in run_debate()."""

    @pytest.mark.asyncio
    async def test_quality_gate_below_60_triggers_fallback(
        self,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Completeness < 60% triggers data-driven fallback without calling agents."""
        # IndicatorSignals with no options-specific signals populated
        # Only rsi populated (1 indicator) -> 1/14 = 7% completeness
        score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(rsi=62.3),
            scan_run_id=1,
        )
        run_agents_mock = AsyncMock()
        monkeypatch.setattr("options_arena.agents.orchestrator._run_agents", run_agents_mock)
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
    async def test_quality_gate_above_60_proceeds(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """Completeness >= 60% allows debate to proceed."""
        # mock_ticker_score has rsi, adx, sma_alignment, bb_width, atr_pct,
        # obv, relative_volume (7 signals), plus contract has greeks (4 more)
        # -> 11/14 = ~79%  which is >= 60%
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
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
    async def test_quality_gate_between_60_80_logs_warning(
        self,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Completeness between 60% and 80% logs a caution warning but proceeds."""
        import logging

        # Build a score with exactly 9 of 14 fields populated = 64%
        score = TickerScore(
            ticker="AAPL",
            composite_score=72.5,
            direction=SignalDirection.BULLISH,
            signals=IndicatorSignals(
                rsi=62.3,
                adx=28.4,
                sma_alignment=0.7,
                bb_width=42.1,
                atr_pct=15.3,
            ),
            scan_run_id=1,
        )
        with (
            caplog.at_level(logging.WARNING, logger="options_arena.agents.orchestrator"),
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
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
# run_debate() — progress callback
# ---------------------------------------------------------------------------


class TestRunDebateProgress:
    """Tests for the optional progress callback parameter."""

    @pytest.mark.asyncio
    async def test_progress_callback_called_on_success(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """Progress callback is called for bull/bear/risk start+complete."""
        from options_arena.agents.orchestrator import DebatePhase

        calls: list[tuple[DebatePhase, str, float | None]] = []

        def on_progress(phase: DebatePhase, status: str, confidence: float | None) -> None:
            calls.append((phase, status, confidence))

        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
                progress=on_progress,
            )
        assert result.is_fallback is False

        # Bull started + completed, Bear started + completed, Risk started + completed
        phases = [(c[0], c[1]) for c in calls]
        assert (DebatePhase.BULL, "started") in phases
        assert (DebatePhase.BULL, "completed") in phases
        assert (DebatePhase.BEAR, "started") in phases
        assert (DebatePhase.BEAR, "completed") in phases
        assert (DebatePhase.RISK, "started") in phases
        assert (DebatePhase.RISK, "completed") in phases

    @pytest.mark.asyncio
    async def test_progress_callback_none_works(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
        mock_debate_config: DebateConfig,
    ) -> None:
        """progress=None (default) works without errors — backward compatible."""
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=mock_debate_config,
                progress=None,
            )
        assert result.is_fallback is False

    @pytest.mark.asyncio
    async def test_progress_callback_error_does_not_crash_debate(
        self,
        mock_ticker_score: TickerScore,
        mock_option_contract: OptionContract,
        mock_quote: Quote,
        mock_ticker_info: TickerInfo,
    ) -> None:
        """A failing progress callback does not crash the debate."""

        def on_progress(
            phase: DebatePhase,
            status: str,
            confidence: float | None,  # noqa: ARG001
        ) -> None:
            raise RuntimeError("callback error")

        config = DebateConfig(
            agent_timeout=10.0,
            max_total_duration=30.0,
        )
        with (
            bull_agent.override(model=TestModel()),
            bear_agent.override(model=TestModel()),
            risk_agent.override(model=TestModel()),
        ):
            result = await run_debate(
                ticker_score=mock_ticker_score,
                contracts=[mock_option_contract],
                quote=mock_quote,
                ticker_info=mock_ticker_info,
                config=config,
                progress=on_progress,
            )
        # Debate succeeds despite callback failures
        assert result.is_fallback is False
