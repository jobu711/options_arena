"""Unit tests for shared model factory functions.

Validates that each factory produces valid model instances with sensible
defaults and supports keyword overrides.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.agents._parsing import DebateResult
from options_arena.models.analysis import (
    AgentResponse,
    MarketContext,
    TradeThesis,
)
from options_arena.models.enums import (
    ExerciseStyle,
    MacdSignal,
    OptionType,
    SignalDirection,
    SpreadType,
)
from options_arena.models.market_data import Quote
from options_arena.models.options import OptionContract
from options_arena.models.scan import TickerScore
from options_arena.models.scoring import DimensionalScores
from options_arena.scan.models import ScanResult
from tests.factories import (
    make_agent_response,
    make_debate_result,
    make_dimensional_scores,
    make_market_context,
    make_option_contract,
    make_quote,
    make_scan_result,
    make_ticker_score,
    make_trade_thesis,
)


class TestMakeOptionContract:
    """Tests for ``make_option_contract()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid OptionContract."""
        contract = make_option_contract()
        assert isinstance(contract, OptionContract)
        assert contract.ticker == "AAPL"
        assert contract.option_type == OptionType.CALL
        assert contract.strike == Decimal("150.00")
        assert contract.volume == 100
        assert contract.open_interest == 500
        assert contract.exercise_style == ExerciseStyle.AMERICAN
        assert contract.market_iv == pytest.approx(0.30, rel=1e-4)
        assert contract.greeks is None

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        contract = make_option_contract(
            ticker="MSFT",
            option_type=OptionType.PUT,
            strike=Decimal("400.00"),
            volume=5000,
            market_iv=0.45,
        )
        assert contract.ticker == "MSFT"
        assert contract.option_type == OptionType.PUT
        assert contract.strike == Decimal("400.00")
        assert contract.volume == 5000
        assert contract.market_iv == pytest.approx(0.45, rel=1e-4)

    def test_computed_fields(self) -> None:
        """Computed fields (mid, spread) are correct."""
        contract = make_option_contract(bid=Decimal("10.00"), ask=Decimal("12.00"))
        assert contract.mid == Decimal("11.00")
        assert contract.spread == Decimal("2.00")

    def test_dte_is_positive(self) -> None:
        """Default DTE is positive (45 days from now)."""
        contract = make_option_contract()
        assert contract.dte > 0


class TestMakeQuote:
    """Tests for ``make_quote()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid Quote."""
        quote = make_quote()
        assert isinstance(quote, Quote)
        assert quote.ticker == "AAPL"
        assert quote.price == Decimal("185.50")
        assert quote.bid == Decimal("185.40")
        assert quote.ask == Decimal("185.60")
        assert quote.volume == 50_000_000
        assert quote.timestamp.tzinfo is not None
        assert quote.timestamp.utcoffset() == timedelta(0)

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        quote = make_quote(ticker="GOOG", price=Decimal("175.00"), volume=100_000)
        assert quote.ticker == "GOOG"
        assert quote.price == Decimal("175.00")
        assert quote.volume == 100_000


class TestMakeMarketContext:
    """Tests for ``make_market_context()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid MarketContext."""
        ctx = make_market_context()
        assert isinstance(ctx, MarketContext)
        assert ctx.ticker == "AAPL"
        assert ctx.current_price == Decimal("185.50")
        assert ctx.macd_signal == MacdSignal.BULLISH_CROSSOVER
        assert ctx.exercise_style == ExerciseStyle.AMERICAN
        assert ctx.composite_score == pytest.approx(72.5, abs=0.01)
        assert ctx.direction_signal == SignalDirection.BULLISH
        assert ctx.data_timestamp.tzinfo is not None

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        ctx = make_market_context(
            ticker="TSLA",
            rsi_14=72.0,
            direction_signal=SignalDirection.BEARISH,
        )
        assert ctx.ticker == "TSLA"
        assert ctx.rsi_14 == pytest.approx(72.0, rel=1e-4)
        assert ctx.direction_signal == SignalDirection.BEARISH


class TestMakeTickerScore:
    """Tests for ``make_ticker_score()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid TickerScore."""
        score = make_ticker_score()
        assert isinstance(score, TickerScore)
        assert score.ticker == "AAPL"
        assert score.composite_score == pytest.approx(72.5, abs=0.01)
        assert score.direction == SignalDirection.BULLISH
        assert score.signals.rsi == pytest.approx(65.0, rel=1e-4)
        assert score.signals.adx == pytest.approx(70.0, rel=1e-4)

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        score = make_ticker_score(ticker="NVDA", composite_score=90.0)
        assert score.ticker == "NVDA"
        assert score.composite_score == pytest.approx(90.0, abs=0.01)


class TestMakeDimensionalScores:
    """Tests for ``make_dimensional_scores()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a DimensionalScores with all None."""
        ds = make_dimensional_scores()
        assert isinstance(ds, DimensionalScores)
        assert ds.trend is None
        assert ds.iv_vol is None
        assert ds.flow is None
        assert ds.risk is None

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        ds = make_dimensional_scores(trend=75.0, risk=40.0)
        assert ds.trend == pytest.approx(75.0, rel=1e-4)
        assert ds.risk == pytest.approx(40.0, rel=1e-4)
        assert ds.iv_vol is None  # not overridden


class TestMakeAgentResponse:
    """Tests for ``make_agent_response()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid AgentResponse."""
        resp = make_agent_response()
        assert isinstance(resp, AgentResponse)
        assert resp.agent_name == "bull"
        assert resp.direction == SignalDirection.BULLISH
        assert resp.confidence == pytest.approx(0.75, abs=0.01)
        assert len(resp.key_points) >= 1
        assert len(resp.risks_cited) >= 1
        assert len(resp.contracts_referenced) >= 1
        assert resp.model_used == "llama-3.3-70b-versatile"

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        resp = make_agent_response(
            agent_name="risk",
            confidence=0.55,
            direction=SignalDirection.NEUTRAL,
        )
        assert resp.agent_name == "risk"
        assert resp.confidence == pytest.approx(0.55, abs=0.01)
        assert resp.direction == SignalDirection.NEUTRAL


class TestMakeTradeThesis:
    """Tests for ``make_trade_thesis()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid TradeThesis."""
        thesis = make_trade_thesis()
        assert isinstance(thesis, TradeThesis)
        assert thesis.ticker == "AAPL"
        assert thesis.direction == SignalDirection.BULLISH
        assert thesis.confidence == pytest.approx(0.70, abs=0.01)
        assert thesis.bull_score == pytest.approx(7.5, abs=0.01)
        assert thesis.bear_score == pytest.approx(4.0, abs=0.01)
        assert len(thesis.key_factors) >= 1

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        thesis = make_trade_thesis(
            ticker="NVDA",
            recommended_strategy=SpreadType.VERTICAL,
        )
        assert thesis.ticker == "NVDA"
        assert thesis.recommended_strategy == SpreadType.VERTICAL


class TestMakeDebateResult:
    """Tests for ``make_debate_result()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid DebateResult."""
        result = make_debate_result()
        assert isinstance(result, DebateResult)
        assert isinstance(result.context, MarketContext)
        assert isinstance(result.bull_response, AgentResponse)
        assert isinstance(result.bear_response, AgentResponse)
        assert isinstance(result.thesis, TradeThesis)
        assert result.bull_response.agent_name == "bull"
        assert result.bear_response.agent_name == "bear"
        assert result.duration_ms == 2500
        assert result.is_fallback is False

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        result = make_debate_result(duration_ms=5000, is_fallback=True)
        assert result.duration_ms == 5000
        assert result.is_fallback is True


class TestMakeScanResult:
    """Tests for ``make_scan_result()``."""

    def test_defaults(self) -> None:
        """Factory with no args produces a valid ScanResult."""
        result = make_scan_result()
        assert isinstance(result, ScanResult)
        assert result.scan_run.preset == "sp500"
        assert result.risk_free_rate == pytest.approx(0.045, rel=1e-4)
        assert result.cancelled is False
        assert result.phases_completed == 4
        assert len(result.scores) == 1
        assert "AAPL" in result.recommendations
        assert len(result.recommendations["AAPL"]) == 1

    def test_overrides(self) -> None:
        """Factory respects keyword overrides."""
        result = make_scan_result(cancelled=True, phases_completed=2)
        assert result.cancelled is True
        assert result.phases_completed == 2


class TestFrozenModelsImmutable:
    """Frozen model factories produce immutable instances."""

    def test_option_contract_frozen(self) -> None:
        """OptionContract rejects attribute mutation."""
        contract = make_option_contract()
        with pytest.raises(ValidationError):
            contract.ticker = "MSFT"

    def test_quote_frozen(self) -> None:
        """Quote rejects attribute mutation."""
        quote = make_quote()
        with pytest.raises(ValidationError):
            quote.ticker = "MSFT"

    def test_agent_response_frozen(self) -> None:
        """AgentResponse rejects attribute mutation."""
        resp = make_agent_response()
        with pytest.raises(ValidationError):
            resp.agent_name = "bear"

    def test_trade_thesis_frozen(self) -> None:
        """TradeThesis rejects attribute mutation."""
        thesis = make_trade_thesis()
        with pytest.raises(ValidationError):
            thesis.ticker = "MSFT"

    def test_dimensional_scores_frozen(self) -> None:
        """DimensionalScores rejects attribute mutation."""
        ds = make_dimensional_scores(trend=50.0)
        with pytest.raises(ValidationError):
            ds.trend = 60.0

    def test_debate_result_frozen(self) -> None:
        """DebateResult rejects attribute mutation."""
        result = make_debate_result()
        with pytest.raises(ValidationError):
            result.duration_ms = 9999


class TestDecimalFieldsAreDecimal:
    """Decimal fields use ``Decimal`` type, not ``float``."""

    def test_option_contract_decimals(self) -> None:
        """OptionContract price fields are Decimal."""
        contract = make_option_contract()
        assert isinstance(contract.strike, Decimal)
        assert isinstance(contract.bid, Decimal)
        assert isinstance(contract.ask, Decimal)
        assert isinstance(contract.last, Decimal)
        assert isinstance(contract.mid, Decimal)
        assert isinstance(contract.spread, Decimal)

    def test_quote_decimals(self) -> None:
        """Quote price fields are Decimal."""
        quote = make_quote()
        assert isinstance(quote.price, Decimal)
        assert isinstance(quote.bid, Decimal)
        assert isinstance(quote.ask, Decimal)

    def test_market_context_decimals(self) -> None:
        """MarketContext price fields are Decimal."""
        ctx = make_market_context()
        assert isinstance(ctx.current_price, Decimal)
        assert isinstance(ctx.price_52w_high, Decimal)
        assert isinstance(ctx.price_52w_low, Decimal)
        assert isinstance(ctx.target_strike, Decimal)


class TestDatetimeFieldsAreUtc:
    """Datetime fields have UTC timezone info."""

    def test_quote_timestamp_utc(self) -> None:
        """Quote timestamp is UTC."""
        quote = make_quote()
        assert quote.timestamp.tzinfo is not None
        assert quote.timestamp.utcoffset() == timedelta(0)

    def test_market_context_data_timestamp_utc(self) -> None:
        """MarketContext data_timestamp is UTC."""
        ctx = make_market_context()
        assert ctx.data_timestamp.tzinfo is not None
        assert ctx.data_timestamp.utcoffset() == timedelta(0)

    def test_scan_result_timestamps_utc(self) -> None:
        """ScanResult scan_run timestamps are UTC."""
        result = make_scan_result()
        assert result.scan_run.started_at.tzinfo is not None
        assert result.scan_run.started_at.utcoffset() == timedelta(0)
        assert result.scan_run.completed_at is not None
        assert result.scan_run.completed_at.tzinfo is not None
        assert result.scan_run.completed_at.utcoffset() == timedelta(0)
