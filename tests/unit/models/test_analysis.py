"""Unit tests for analysis models: MarketContext, AgentResponse, TradeThesis, VolatilityThesis.

Tests cover:
- Happy path construction with all fields
- MarketContext is NOT frozen (mutable)
- AgentResponse frozen enforcement and confidence validation
- TradeThesis frozen enforcement and default values
- VolatilityThesis frozen enforcement, confidence validation, and JSON roundtrip
- JSON serialization roundtrip
"""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from options_arena.models import (
    AgentResponse,
    ExerciseStyle,
    MacdSignal,
    MarketContext,
    SignalDirection,
    SpreadType,
    TradeThesis,
    VolatilityThesis,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_market_context() -> MarketContext:
    """Create a valid MarketContext instance for reuse."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("186.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.0,
        iv_percentile=52.0,
        atm_iv_30d=0.28,
        rsi_14=42.0,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=date(2025, 7, 24),
        dte_target=45,
        target_strike=Decimal("185.00"),
        target_delta=0.35,
        sector="Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_agent_response() -> AgentResponse:
    """Create a valid AgentResponse instance for reuse."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        argument="RSI at 42 suggests oversold conditions with upside potential.",
        key_points=["RSI oversold", "Strong support at 180"],
        risks_cited=["Earnings uncertainty", "Broad market weakness"],
        contracts_referenced=["AAPL 185C 2025-09-19"],
        model_used="llama3.1:8b",
    )


@pytest.fixture
def sample_trade_thesis() -> TradeThesis:
    """Create a valid TradeThesis instance for reuse."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        summary="Bull case prevails with RSI oversold and strong support.",
        bull_score=7.5,
        bear_score=4.2,
        key_factors=["RSI oversold", "Support at 180", "Earnings catalyst"],
        risk_assessment="Moderate risk due to earnings uncertainty.",
    )


# ---------------------------------------------------------------------------
# MarketContext Tests
# ---------------------------------------------------------------------------


class TestMarketContext:
    """Tests for the MarketContext model."""

    def test_happy_path_all_fields(self, sample_market_context: MarketContext) -> None:
        """MarketContext constructs with all fields correctly assigned."""
        assert sample_market_context.ticker == "AAPL"
        assert sample_market_context.current_price == Decimal("186.50")
        assert sample_market_context.price_52w_high == Decimal("199.62")
        assert sample_market_context.price_52w_low == Decimal("164.08")
        assert sample_market_context.iv_rank == pytest.approx(45.0)
        assert sample_market_context.iv_percentile == pytest.approx(52.0)
        assert sample_market_context.atm_iv_30d == pytest.approx(0.28)
        assert sample_market_context.rsi_14 == pytest.approx(42.0)
        assert sample_market_context.macd_signal == MacdSignal.BULLISH_CROSSOVER
        assert sample_market_context.put_call_ratio == pytest.approx(0.85)
        assert sample_market_context.next_earnings == date(2025, 7, 24)
        assert sample_market_context.dte_target == 45
        assert sample_market_context.target_strike == Decimal("185.00")
        assert sample_market_context.target_delta == pytest.approx(0.35)
        assert sample_market_context.sector == "Technology"
        assert sample_market_context.dividend_yield == pytest.approx(0.005)
        assert sample_market_context.exercise_style == ExerciseStyle.AMERICAN

    def test_not_frozen_can_mutate(self, sample_market_context: MarketContext) -> None:
        """MarketContext is NOT frozen: fields can be reassigned."""
        sample_market_context.ticker = "MSFT"
        assert sample_market_context.ticker == "MSFT"
        sample_market_context.rsi_14 = 55.0
        assert sample_market_context.rsi_14 == pytest.approx(55.0)

    def test_next_earnings_accepts_none(self) -> None:
        """MarketContext next_earnings field accepts None."""
        ctx = MarketContext(
            ticker="TSLA",
            current_price=Decimal("250.00"),
            price_52w_high=Decimal("300.00"),
            price_52w_low=Decimal("150.00"),
            iv_rank=60.0,
            iv_percentile=65.0,
            atm_iv_30d=0.55,
            rsi_14=50.0,
            macd_signal=MacdSignal.NEUTRAL,
            put_call_ratio=1.0,
            next_earnings=None,
            dte_target=45,
            target_strike=Decimal("250.00"),
            target_delta=0.35,
            sector="Automotive",
            dividend_yield=0.0,
            exercise_style=ExerciseStyle.AMERICAN,
            data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
        )
        assert ctx.next_earnings is None

    def test_naive_timestamp_raises(self) -> None:
        """MarketContext rejects naive datetime for data_timestamp."""
        with pytest.raises(ValidationError, match="UTC"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                iv_rank=45.0,
                iv_percentile=52.0,
                atm_iv_30d=0.28,
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                put_call_ratio=0.85,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0),  # naive
            )

    def test_non_utc_timestamp_raises(self) -> None:
        """MarketContext rejects non-UTC timezone for data_timestamp."""
        est = timezone(timedelta(hours=-5))
        with pytest.raises(ValidationError, match="UTC"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                iv_rank=45.0,
                iv_percentile=52.0,
                atm_iv_30d=0.28,
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                put_call_ratio=0.85,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=est),
            )

    def test_json_roundtrip(self, sample_market_context: MarketContext) -> None:
        """MarketContext survives JSON serialization/deserialization unchanged."""
        json_str = sample_market_context.model_dump_json()
        restored = MarketContext.model_validate_json(json_str)
        assert restored == sample_market_context

    def test_iv_rank_nan_raises(self) -> None:
        """MarketContext rejects NaN iv_rank."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                iv_rank=float("nan"),
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
            )

    def test_iv_percentile_inf_raises(self) -> None:
        """MarketContext rejects Inf iv_percentile."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                iv_percentile=float("inf"),
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
            )

    def test_put_call_ratio_nan_raises(self) -> None:
        """MarketContext rejects NaN put_call_ratio."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                put_call_ratio=float("nan"),
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
            )

    def test_atm_iv_30d_neg_inf_raises(self) -> None:
        """MarketContext rejects -Inf atm_iv_30d."""
        with pytest.raises(ValidationError, match="finite"):
            MarketContext(
                ticker="AAPL",
                current_price=Decimal("186.50"),
                price_52w_high=Decimal("199.62"),
                price_52w_low=Decimal("164.08"),
                atm_iv_30d=float("-inf"),
                rsi_14=42.0,
                macd_signal=MacdSignal.BULLISH_CROSSOVER,
                next_earnings=None,
                dte_target=45,
                target_strike=Decimal("185.00"),
                target_delta=0.35,
                sector="Technology",
                dividend_yield=0.005,
                exercise_style=ExerciseStyle.AMERICAN,
                data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
            )

    def test_optional_floats_accept_none(self) -> None:
        """MarketContext accepts None for iv_rank, iv_percentile, atm_iv_30d, put_call_ratio."""
        ctx = MarketContext(
            ticker="AAPL",
            current_price=Decimal("186.50"),
            price_52w_high=Decimal("199.62"),
            price_52w_low=Decimal("164.08"),
            rsi_14=42.0,
            macd_signal=MacdSignal.BULLISH_CROSSOVER,
            next_earnings=None,
            dte_target=45,
            target_strike=Decimal("185.00"),
            target_delta=0.35,
            sector="Technology",
            dividend_yield=0.005,
            exercise_style=ExerciseStyle.AMERICAN,
            data_timestamp=datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC),
        )
        assert ctx.iv_rank is None
        assert ctx.iv_percentile is None
        assert ctx.atm_iv_30d is None
        assert ctx.put_call_ratio is None


# ---------------------------------------------------------------------------
# AgentResponse Tests
# ---------------------------------------------------------------------------


class TestAgentResponse:
    """Tests for the AgentResponse model."""

    def test_happy_path_construction(self, sample_agent_response: AgentResponse) -> None:
        """AgentResponse constructs with all fields correctly assigned."""
        assert sample_agent_response.agent_name == "bull"
        assert sample_agent_response.direction == SignalDirection.BULLISH
        assert sample_agent_response.confidence == pytest.approx(0.75)
        assert "RSI" in sample_agent_response.argument
        assert len(sample_agent_response.key_points) == 2
        assert len(sample_agent_response.risks_cited) == 2
        assert len(sample_agent_response.contracts_referenced) == 1
        assert sample_agent_response.model_used == "llama3.1:8b"

    def test_frozen_enforcement(self, sample_agent_response: AgentResponse) -> None:
        """AgentResponse is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_agent_response.confidence = 0.5  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """AgentResponse rejects confidence > 1.0 with ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            AgentResponse(
                agent_name="bull",
                direction=SignalDirection.BULLISH,
                confidence=1.5,
                argument="Test argument.",
                key_points=["point"],
                risks_cited=["risk"],
                contracts_referenced=["AAPL 185C"],
                model_used="llama3.1:8b",
            )

    def test_confidence_too_low_raises(self) -> None:
        """AgentResponse rejects confidence < 0.0 with ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            AgentResponse(
                agent_name="bear",
                direction=SignalDirection.BEARISH,
                confidence=-0.1,
                argument="Test argument.",
                key_points=["point"],
                risks_cited=["risk"],
                contracts_referenced=["AAPL 185P"],
                model_used="llama3.1:8b",
            )

    def test_confidence_boundary_zero(self) -> None:
        """AgentResponse accepts confidence = 0.0 (lower boundary)."""
        resp = AgentResponse(
            agent_name="risk",
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            argument="No conviction.",
            key_points=["uncertain outlook"],
            risks_cited=["high uncertainty"],
            contracts_referenced=[],
            model_used="llama3.1:8b",
        )
        assert resp.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self) -> None:
        """AgentResponse accepts confidence = 1.0 (upper boundary)."""
        resp = AgentResponse(
            agent_name="bull",
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            argument="Maximum conviction.",
            key_points=["strong signal"],
            risks_cited=["minimal downside risk"],
            contracts_referenced=["SPY 450C"],
            model_used="llama3.1:8b",
        )
        assert resp.confidence == pytest.approx(1.0)

    def test_json_roundtrip(self, sample_agent_response: AgentResponse) -> None:
        """AgentResponse survives JSON serialization/deserialization unchanged."""
        json_str = sample_agent_response.model_dump_json()
        restored = AgentResponse.model_validate_json(json_str)
        assert restored == sample_agent_response

    def test_empty_key_points_raises(self) -> None:
        """AgentResponse rejects empty key_points list."""
        with pytest.raises(ValidationError, match="key_points must have at least 1"):
            AgentResponse(
                agent_name="bull",
                direction=SignalDirection.BULLISH,
                confidence=0.7,
                argument="Test.",
                key_points=[],
                risks_cited=["risk"],
                contracts_referenced=[],
                model_used="llama3.1:8b",
            )

    def test_empty_risks_cited_raises(self) -> None:
        """AgentResponse rejects empty risks_cited list."""
        with pytest.raises(ValidationError, match="risks_cited must have at least 1"):
            AgentResponse(
                agent_name="bear",
                direction=SignalDirection.BEARISH,
                confidence=0.6,
                argument="Test.",
                key_points=["point"],
                risks_cited=[],
                contracts_referenced=[],
                model_used="llama3.1:8b",
            )


# ---------------------------------------------------------------------------
# TradeThesis Tests
# ---------------------------------------------------------------------------


class TestTradeThesis:
    """Tests for the TradeThesis model."""

    def test_happy_path_construction(self, sample_trade_thesis: TradeThesis) -> None:
        """TradeThesis constructs with all fields correctly assigned."""
        assert sample_trade_thesis.ticker == "AAPL"
        assert sample_trade_thesis.direction == SignalDirection.BULLISH
        assert sample_trade_thesis.confidence == pytest.approx(0.70)
        assert "Bull case" in sample_trade_thesis.summary
        assert sample_trade_thesis.bull_score == pytest.approx(7.5)
        assert sample_trade_thesis.bear_score == pytest.approx(4.2)
        assert len(sample_trade_thesis.key_factors) == 3
        assert "Moderate risk" in sample_trade_thesis.risk_assessment

    def test_frozen_enforcement(self, sample_trade_thesis: TradeThesis) -> None:
        """TradeThesis is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_trade_thesis.ticker = "MSFT"  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """TradeThesis rejects confidence > 1.0 with ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            TradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=1.5,
                summary="Test summary.",
                bull_score=7.5,
                bear_score=4.2,
                key_factors=["factor"],
                risk_assessment="Low risk.",
            )

    def test_confidence_too_low_raises(self) -> None:
        """TradeThesis rejects confidence < 0.0 with ValidationError."""
        with pytest.raises(ValidationError, match="confidence"):
            TradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BEARISH,
                confidence=-0.1,
                summary="Test summary.",
                bull_score=3.0,
                bear_score=6.0,
                key_factors=["factor"],
                risk_assessment="Moderate risk.",
            )

    def test_confidence_boundary_zero(self) -> None:
        """TradeThesis accepts confidence = 0.0 (lower boundary)."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            summary="No conviction.",
            bull_score=5.0,
            bear_score=5.0,
            key_factors=["inconclusive data"],
            risk_assessment="Uncertain.",
        )
        assert thesis.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self) -> None:
        """TradeThesis accepts confidence = 1.0 (upper boundary)."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            summary="Maximum conviction.",
            bull_score=10.0,
            bear_score=0.0,
            key_factors=["strong signal"],
            risk_assessment="Low risk.",
        )
        assert thesis.confidence == pytest.approx(1.0)

    def test_recommended_strategy_defaults_to_none(self) -> None:
        """TradeThesis recommended_strategy defaults to None."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.65,
            summary="Test summary.",
            bull_score=6.0,
            bear_score=4.0,
            key_factors=["factor1"],
            risk_assessment="Low risk.",
        )
        assert thesis.recommended_strategy is None

    def test_recommended_strategy_accepts_spread_type(self) -> None:
        """TradeThesis recommended_strategy accepts a SpreadType value."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.80,
            summary="Strong bull signal suggests vertical spread.",
            bull_score=8.0,
            bear_score=3.0,
            key_factors=["strong momentum", "RSI oversold"],
            risk_assessment="Low risk.",
            recommended_strategy=SpreadType.VERTICAL,
        )
        assert thesis.recommended_strategy == SpreadType.VERTICAL

    def test_json_roundtrip(self, sample_trade_thesis: TradeThesis) -> None:
        """TradeThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_trade_thesis.model_dump_json()
        restored = TradeThesis.model_validate_json(json_str)
        assert restored == sample_trade_thesis

    def test_json_roundtrip_with_strategy(self) -> None:
        """TradeThesis with recommended_strategy set survives JSON roundtrip."""
        thesis = TradeThesis(
            ticker="SPY",
            direction=SignalDirection.BEARISH,
            confidence=0.60,
            summary="Bear case with iron condor strategy.",
            bull_score=3.5,
            bear_score=6.5,
            key_factors=["high IV"],
            risk_assessment="Moderate risk.",
            recommended_strategy=SpreadType.IRON_CONDOR,
        )
        json_str = thesis.model_dump_json()
        restored = TradeThesis.model_validate_json(json_str)
        assert restored == thesis
        assert restored.recommended_strategy == SpreadType.IRON_CONDOR

    def test_empty_key_factors_raises(self) -> None:
        """TradeThesis rejects empty key_factors list."""
        with pytest.raises(ValidationError, match="key_factors must have at least 1"):
            TradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.65,
                summary="Test summary.",
                bull_score=7.0,
                bear_score=4.0,
                key_factors=[],
                risk_assessment="Low risk.",
            )

    def test_score_confidence_clamp_bull_score_higher_but_bearish(self) -> None:
        """Confidence clamped to 0.5 when bull_score > bear_score but direction is BEARISH."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BEARISH,
            confidence=0.8,
            summary="Contradictory scores.",
            bull_score=7.0,
            bear_score=4.0,
            key_factors=["mismatch"],
            risk_assessment="High risk.",
        )
        assert thesis.confidence == pytest.approx(0.5)

    def test_score_confidence_clamp_bear_score_higher_but_bullish(self) -> None:
        """Confidence clamped to 0.5 when bear_score > bull_score but direction is BULLISH."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.9,
            summary="Contradictory scores.",
            bull_score=3.0,
            bear_score=7.0,
            key_factors=["mismatch"],
            risk_assessment="High risk.",
        )
        assert thesis.confidence == pytest.approx(0.5)

    def test_score_confidence_clamp_low_scores(self) -> None:
        """Confidence clamped when max score < 4.0."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            summary="Weak conviction.",
            bull_score=3.5,
            bear_score=2.0,
            key_factors=["low conviction"],
            risk_assessment="Uncertain.",
        )
        assert thesis.confidence == pytest.approx(0.5)

    def test_score_confidence_no_clamp_when_consistent(self) -> None:
        """Confidence not clamped when scores are consistent with direction."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.8,
            summary="Consistent bull case.",
            bull_score=7.5,
            bear_score=3.5,
            key_factors=["strong momentum"],
            risk_assessment="Low risk.",
        )
        assert thesis.confidence == pytest.approx(0.8)

    def test_score_confidence_no_clamp_already_below_threshold(self) -> None:
        """Confidence already <= 0.5 is not clamped further."""
        thesis = TradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BEARISH,
            confidence=0.4,
            summary="Low confidence bearish.",
            bull_score=6.0,
            bear_score=4.0,
            key_factors=["some signal"],
            risk_assessment="Moderate risk.",
        )
        assert thesis.confidence == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# VolatilityThesis Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_volatility_thesis() -> VolatilityThesis:
    """Create a valid VolatilityThesis instance for reuse."""
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 85th percentile — historically elevated.",
        confidence=0.72,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="High IV favors premium-selling strategies.",
        target_iv_entry=0.35,
        target_iv_exit=0.22,
        suggested_strikes=["AAPL 185P 2025-09-19", "AAPL 195C 2025-09-19"],
        key_vol_factors=["Earnings in 14 days", "IV rank 85th pct", "VIX elevated"],
        model_used="llama3.1:8b",
    )


class TestVolatilityThesis:
    """Tests for the VolatilityThesis model."""

    def test_volatility_thesis_construction(
        self, sample_volatility_thesis: VolatilityThesis
    ) -> None:
        """VolatilityThesis constructs with valid data, all fields correctly assigned."""
        vt = sample_volatility_thesis
        assert vt.iv_assessment == "overpriced"
        assert "85th percentile" in vt.iv_rank_interpretation
        assert vt.confidence == pytest.approx(0.72)
        assert vt.recommended_strategy == SpreadType.IRON_CONDOR
        assert "premium-selling" in vt.strategy_rationale
        assert vt.target_iv_entry == pytest.approx(0.35)
        assert vt.target_iv_exit == pytest.approx(0.22)
        assert len(vt.suggested_strikes) == 2
        assert len(vt.key_vol_factors) == 3
        assert vt.model_used == "llama3.1:8b"

    def test_volatility_thesis_frozen(self, sample_volatility_thesis: VolatilityThesis) -> None:
        """VolatilityThesis is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_volatility_thesis.confidence = 0.5  # type: ignore[misc]

    def test_volatility_thesis_confidence_validation(self) -> None:
        """VolatilityThesis rejects confidence < 0, > 1, NaN, and inf."""
        base_kwargs = {
            "iv_assessment": "fair",
            "iv_rank_interpretation": "IV rank at 50th percentile.",
            "recommended_strategy": None,
            "strategy_rationale": "Neutral vol outlook.",
            "suggested_strikes": [],
            "key_vol_factors": ["IV near median"],
            "model_used": "llama3.1:8b",
        }

        # Reject confidence < 0
        with pytest.raises(ValidationError, match="confidence"):
            VolatilityThesis(confidence=-0.1, **base_kwargs)

        # Reject confidence > 1
        with pytest.raises(ValidationError, match="confidence"):
            VolatilityThesis(confidence=1.5, **base_kwargs)

        # Reject NaN
        with pytest.raises(ValidationError, match="confidence"):
            VolatilityThesis(confidence=float("nan"), **base_kwargs)

        # Reject inf
        with pytest.raises(ValidationError, match="confidence"):
            VolatilityThesis(confidence=float("inf"), **base_kwargs)

    def test_volatility_thesis_json_roundtrip(
        self, sample_volatility_thesis: VolatilityThesis
    ) -> None:
        """VolatilityThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_volatility_thesis.model_dump_json()
        restored = VolatilityThesis.model_validate_json(json_str)
        assert restored == sample_volatility_thesis


# ---------------------------------------------------------------------------
# MarketContext completeness_ratio Tests
# ---------------------------------------------------------------------------


class TestCompletenessRatio:
    """Tests for MarketContext.completeness_ratio() method."""

    def _make_context(self, **overrides: object) -> MarketContext:
        """Build a MarketContext with minimal required fields and optional overrides."""
        defaults: dict[str, object] = {
            "ticker": "AAPL",
            "current_price": Decimal("185.50"),
            "price_52w_high": Decimal("199.62"),
            "price_52w_low": Decimal("164.08"),
            "rsi_14": 50.0,
            "macd_signal": MacdSignal.NEUTRAL,
            "next_earnings": None,
            "dte_target": 45,
            "target_strike": Decimal("185.00"),
            "target_delta": 0.35,
            "sector": "Technology",
            "dividend_yield": 0.005,
            "exercise_style": ExerciseStyle.AMERICAN,
            "data_timestamp": datetime(2026, 2, 25, 14, 0, 0, tzinfo=UTC),
        }
        defaults.update(overrides)
        return MarketContext(**defaults)  # type: ignore[arg-type]

    def test_completeness_all_none(self) -> None:
        """All optional fields None returns 0.0."""
        ctx = self._make_context()
        assert ctx.completeness_ratio() == pytest.approx(0.0)

    def test_completeness_all_populated_with_contracts(self) -> None:
        """All 14 optional fields populated (with contract) returns 1.0."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            atm_iv_30d=0.28,
            put_call_ratio=0.85,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            stochastic_rsi=55.0,
            relative_volume=65.0,
            target_gamma=0.025,
            target_theta=-0.045,
            target_vega=0.32,
            target_rho=0.08,
            contract_mid=Decimal("3.50"),
        )
        assert ctx.completeness_ratio() == pytest.approx(1.0)

    def test_completeness_all_indicators_no_contract(self) -> None:
        """All 10 indicator fields populated without contract returns 1.0."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            atm_iv_30d=0.28,
            put_call_ratio=0.85,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            atr_pct=15.3,
            stochastic_rsi=55.0,
            relative_volume=65.0,
        )
        assert ctx.completeness_ratio() == pytest.approx(1.0)

    def test_completeness_partial_no_contract(self) -> None:
        """7 of 10 indicator fields populated (no contract) returns 0.7."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            atm_iv_30d=0.28,
            put_call_ratio=0.85,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
        )
        assert ctx.completeness_ratio() == pytest.approx(7.0 / 10.0)

    def test_completeness_partial_with_contract(self) -> None:
        """7 indicator + 4 Greeks of 14 total (with contract) returns 11/14."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            atm_iv_30d=0.28,
            put_call_ratio=0.85,
            adx=28.4,
            sma_alignment=0.7,
            bb_width=42.1,
            target_gamma=0.025,
            target_theta=-0.045,
            target_vega=0.32,
            target_rho=0.08,
            contract_mid=Decimal("3.50"),
        )
        assert ctx.completeness_ratio() == pytest.approx(11.0 / 14.0)

    def test_completeness_some_none_no_contract(self) -> None:
        """2 indicator fields populated (no contract, Greeks ignored) returns 2/10."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            # target_gamma/theta set but ignored without contract_mid
            target_gamma=0.025,
            target_theta=-0.045,
        )
        assert ctx.completeness_ratio() == pytest.approx(2.0 / 10.0)

    def test_completeness_some_none_with_contract(self) -> None:
        """4 of 14 fields populated (with contract) returns 4/14."""
        ctx = self._make_context(
            iv_rank=45.0,
            iv_percentile=52.0,
            target_gamma=0.025,
            target_theta=-0.045,
            contract_mid=Decimal("2.10"),
        )
        assert ctx.completeness_ratio() == pytest.approx(4.0 / 14.0)

    def test_completeness_zero_values_count_as_populated(self) -> None:
        """Zero float values are NOT None — they count as populated."""
        ctx = self._make_context(
            iv_rank=0.0,
            iv_percentile=0.0,
            put_call_ratio=0.0,
        )
        # No contract_mid → denominator is 10 (indicators only)
        assert ctx.completeness_ratio() == pytest.approx(3.0 / 10.0)
