"""Shared model factory functions for Options Arena tests.

Each factory returns a fully-valid model instance with sensible defaults.
All parameters are keyword-only with ``**kw`` overrides for any field.
No external dependencies (no ``factory_boy``, no ``faker``).

Usage::

    from tests.factories import make_option_contract, make_quote

    contract = make_option_contract()               # all defaults
    contract = make_option_contract(ticker="MSFT")   # override ticker
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.models.analysis import (
    AgentResponse,
    MarketContext,
    TradeThesis,
)
from options_arena.models.enums import (
    DeskType,
    ExerciseStyle,
    MacdSignal,
    OptionType,
    PositionSide,
    ScanPreset,
    ScanSource,
    SignalDirection,
    SpreadType,
)
from options_arena.models.market_data import Quote
from options_arena.models.options import OptionContract, OptionSpread, SpreadAnalysis, SpreadLeg
from options_arena.models.recommendation import (
    AnyAssessment,
    DomainAssessment,
    FlowAssessment,
    FundamentalAssessment,
    PositionRecommendation,
    RecommendationResult,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.models.scan import IndicatorSignals, ScanRun, TickerScore
from options_arena.models.scoring import DimensionalScores
from options_arena.scan.models import ScanResult


def make_option_contract(**kw: object) -> OptionContract:
    """Create a test ``OptionContract`` with sensible defaults.

    Defaults produce a valid AAPL call, 45 DTE, American-style.
    All ``Decimal`` fields constructed from strings.
    """
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "option_type": OptionType.CALL,
        "strike": Decimal("150.00"),
        "expiration": datetime.now(UTC).date() + timedelta(days=45),
        "bid": Decimal("5.00"),
        "ask": Decimal("5.50"),
        "last": Decimal("5.25"),
        "volume": 100,
        "open_interest": 500,
        "exercise_style": ExerciseStyle.AMERICAN,
        "market_iv": 0.30,
    }
    defaults.update(kw)
    return OptionContract(**defaults)


def make_quote(**kw: object) -> Quote:
    """Create a test ``Quote`` with sensible defaults.

    Defaults produce a valid AAPL quote with UTC timestamp.
    """
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "price": Decimal("185.50"),
        "bid": Decimal("185.40"),
        "ask": Decimal("185.60"),
        "volume": 50_000_000,
        "timestamp": datetime.now(UTC),
    }
    defaults.update(kw)
    return Quote(**defaults)


def make_market_context(**kw: object) -> MarketContext:
    """Create a test ``MarketContext`` with sensible defaults.

    Defaults produce a complete context for AAPL with all required fields
    populated and optional fields set to representative values.
    """
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "current_price": Decimal("185.50"),
        "price_52w_high": Decimal("200.00"),
        "price_52w_low": Decimal("140.00"),
        "iv_rank": 45.0,
        "iv_percentile": 50.0,
        "atm_iv_30d": 0.28,
        "rsi_14": 55.0,
        "macd_signal": MacdSignal.BULLISH_CROSSOVER,
        "put_call_ratio": 0.85,
        "max_pain_distance": 2.5,
        "next_earnings": datetime.now(UTC).date() + timedelta(days=30),
        "dte_target": 45,
        "target_strike": Decimal("185.00"),
        "target_delta": 0.35,
        "sector": "Information Technology",
        "dividend_yield": 0.005,
        "exercise_style": ExerciseStyle.AMERICAN,
        "data_timestamp": datetime.now(UTC),
        "composite_score": 72.5,
        "direction_signal": SignalDirection.BULLISH,
    }
    defaults.update(kw)
    return MarketContext(**defaults)


def make_ticker_score(**kw: object) -> TickerScore:
    """Create a test ``TickerScore`` with sensible defaults.

    Defaults produce a bullish AAPL score with populated indicator signals.
    """
    signals_kw: dict[str, object] = {}
    if "signals" not in kw:
        signals_kw = {
            "rsi": 65.0,
            "adx": 70.0,
            "sma_alignment": 80.0,
            "bb_width": 40.0,
            "atr_pct": 35.0,
            "relative_volume": 55.0,
        }
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "composite_score": 72.5,
        "direction": SignalDirection.BULLISH,
        "signals": IndicatorSignals(**signals_kw),
    }
    defaults.update(kw)
    return TickerScore(**defaults)


def make_dimensional_scores(**kw: object) -> DimensionalScores:
    """Create a test ``DimensionalScores`` with sensible defaults.

    All scores default to ``None`` (the model's own default).
    Override any score via keyword arguments.
    """
    defaults: dict[str, object] = {
        "trend": None,
        "iv_vol": None,
        "hv_vol": None,
        "flow": None,
        "microstructure": None,
        "fundamental": None,
        "regime": None,
        "risk": None,
    }
    defaults.update(kw)
    return DimensionalScores(**defaults)


def make_agent_response(**kw: object) -> AgentResponse:
    """Create a test ``AgentResponse`` with sensible defaults.

    Defaults produce a valid bullish bull agent response.
    """
    defaults: dict[str, object] = {
        "agent_name": "bull",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "argument": "Strong uptrend with supportive technicals and momentum.",
        "key_points": ["RSI above 60 confirms momentum", "SMA alignment bullish"],
        "risks_cited": ["Earnings in 30 days could cause volatility"],
        "contracts_referenced": ["AAPL 185C 2026-04-15"],
        "model_used": "llama-3.3-70b-versatile",
    }
    defaults.update(kw)
    return AgentResponse(**defaults)


def make_trade_thesis(**kw: object) -> TradeThesis:
    """Create a test ``TradeThesis`` with sensible defaults.

    Defaults produce a valid bullish thesis for AAPL.
    Note: ``bull_score`` > ``bear_score`` and direction is BULLISH
    to avoid confidence clamping by the model validator.
    """
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.70,
        "summary": "Bullish outlook supported by technicals and momentum.",
        "bull_score": 7.5,
        "bear_score": 4.0,
        "key_factors": ["Strong uptrend", "Healthy volume"],
        "risk_assessment": "Moderate risk due to upcoming earnings.",
        "recommended_strategy": None,
    }
    defaults.update(kw)
    return TradeThesis(**defaults)


def make_debate_result(**kw: object) -> DebateResult:
    """Create a test ``DebateResult`` with sensible defaults.

    Uses sub-factories internally for ``context``, ``bull_response``,
    ``bear_response``, and ``thesis``.
    """
    defaults: dict[str, object] = {
        "context": make_market_context(),
        "bull_response": make_agent_response(agent_name="bull"),
        "bear_response": make_agent_response(
            agent_name="bear",
            direction=SignalDirection.BEARISH,
            confidence=0.60,
            argument="Overbought conditions and earnings risk.",
            key_points=["RSI elevated", "Earnings uncertainty"],
            risks_cited=["Potential IV crush post-earnings"],
            contracts_referenced=["AAPL 180P 2026-04-15"],
        ),
        "thesis": make_trade_thesis(),
        "total_usage": RunUsage(),
        "duration_ms": 2500,
        "is_fallback": False,
    }
    defaults.update(kw)
    return DebateResult(**defaults)


def make_spread_leg(**kw: object) -> SpreadLeg:
    """Create a test ``SpreadLeg`` with sensible defaults.

    Defaults produce a long AAPL call leg with 1 contract.
    """
    defaults: dict[str, object] = {
        "contract": make_option_contract(),
        "side": PositionSide.LONG,
        "quantity": 1,
    }
    defaults.update(kw)
    return SpreadLeg(**defaults)


def make_spread_analysis(**kw: object) -> SpreadAnalysis:
    """Create a test ``SpreadAnalysis`` with sensible defaults.

    Defaults produce a valid bull call vertical spread analysis on AAPL.
    Long 150 call / short 155 call, debit spread.
    """
    long_leg = make_spread_leg(
        contract=make_option_contract(strike=Decimal("150.00")),
        side=PositionSide.LONG,
    )
    short_leg = make_spread_leg(
        contract=make_option_contract(strike=Decimal("155.00")),
        side=PositionSide.SHORT,
    )
    spread = OptionSpread(
        spread_type=SpreadType.VERTICAL,
        legs=[long_leg, short_leg],
        ticker="AAPL",
    )
    defaults: dict[str, object] = {
        "spread": spread,
        "net_premium": Decimal("2.50"),
        "max_profit": Decimal("2.50"),
        "max_loss": Decimal("2.50"),
        "breakevens": [Decimal("152.50")],
        "risk_reward_ratio": 1.0,
        "pop_estimate": 0.55,
    }
    defaults.update(kw)
    return SpreadAnalysis(**defaults)


def make_scan_result(**kw: object) -> ScanResult:
    """Create a test ``ScanResult`` with sensible defaults.

    Defaults produce a minimal completed scan with one scored ticker
    and one recommendation.
    """
    now_utc = datetime.now(UTC)
    default_contract = make_option_contract()
    default_score = make_ticker_score()

    defaults: dict[str, object] = {
        "scan_run": ScanRun(
            id=1,
            started_at=now_utc - timedelta(minutes=5),
            completed_at=now_utc,
            preset=ScanPreset.SP500,
            source=ScanSource.MANUAL,
            tickers_scanned=500,
            tickers_scored=450,
            recommendations=50,
        ),
        "scores": [default_score],
        "recommendations": {"AAPL": [default_contract]},
        "risk_free_rate": 0.045,
        "earnings_dates": {},
        "cancelled": False,
        "phases_completed": 4,
    }
    defaults.update(kw)
    return ScanResult(**defaults)


def make_domain_assessment(desk: DeskType = DeskType.TREND, **kw: object) -> DomainAssessment:
    """Create a test ``DomainAssessment`` (concrete subclass) with sensible defaults.

    Returns the correct desk-specific subclass based on ``desk``.  Override any
    base-class or subclass field via keyword arguments.
    """
    base: dict[str, object] = {
        "direction": SignalDirection.BULLISH,
        "confidence": 0.72,
        "summary": f"{desk.value.title()} desk assessment for test.",
        "key_factors": ["Test factor 1", "Test factor 2"],
        "risks": ["Test risk"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_quote"],
        "model_used": "test",
    }
    base.update(kw)

    match desk:
        case DeskType.TREND:
            return TrendAssessment(**base, trend_strength=base.pop("trend_strength", 0.8))  # type: ignore[arg-type]
        case DeskType.VOLATILITY:
            return VolatilityAssessment(**base)  # type: ignore[arg-type]
        case DeskType.FLOW:
            return FlowAssessment(**base)  # type: ignore[arg-type]
        case DeskType.FUNDAMENTAL:
            return FundamentalAssessment(**base)  # type: ignore[arg-type]
        case DeskType.RISK:
            return RiskDeskAssessment(
                **base,  # type: ignore[arg-type]
                max_position_pct=base.pop("max_position_pct", 0.05),  # type: ignore[arg-type]
            )
        case DeskType.CONTRARIAN:
            from options_arena.models.recommendation import ContrarianAssessment

            return ContrarianAssessment(**base)  # type: ignore[arg-type]
        case _:
            return TrendAssessment(**base)  # type: ignore[arg-type]


def make_position_recommendation(
    direction: SignalDirection = SignalDirection.BULLISH, **kw: object
) -> PositionRecommendation:
    """Create a test ``PositionRecommendation`` with sensible defaults.

    Defaults produce a valid AAPL bullish position recommendation.
    """
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": direction,
        "confidence": 0.70,
        "recommended_contract": "AAPL 190C 2026-04-18",
        "entry_price": Decimal("5.25"),
        "entry_criteria": "Enter on pullback to support.",
        "exit_criteria": "Exit at 50% profit or 30% loss.",
        "stop_loss": Decimal("3.50"),
        "take_profit": Decimal("7.80"),
        "position_size_pct": 0.05,
        "position_rationale": "Conservative size due to earnings.",
        "risk_reward_ratio": 2.3,
        "max_loss_estimate": "$175 per contract",
        "recommended_strategy": None,
        "strategy_rationale": "Directional call with limited risk.",
        "summary": "Bullish momentum with moderate IV entry.",
        "key_factors": ["RSI at 65", "IV rank 45"],
        "risk_assessment": "Moderate risk; earnings in 7 days.",
        "agent_agreement_score": 0.8,
        "dissenting_desks": [],
        "model_used": "test",
    }
    defaults.update(kw)
    return PositionRecommendation(**defaults)


def make_recommendation_result(
    ticker: str = "AAPL", is_fallback: bool = False, **kw: object
) -> RecommendationResult:
    """Create a test ``RecommendationResult`` with sensible defaults.

    Builds a complete recommendation with 2 assessments (Trend + Volatility),
    a ``PositionRecommendation``, and a ``MarketContext``.
    """
    context = make_market_context(ticker=ticker)
    trend = make_domain_assessment(DeskType.TREND)
    vol = make_domain_assessment(DeskType.VOLATILITY, confidence=0.65)
    assessments: list[AnyAssessment] = [trend, vol]  # type: ignore[list-item]
    recommendation = make_position_recommendation(ticker=ticker)

    defaults: dict[str, object] = {
        "context": context,
        "assessments": assessments,
        "recommendation": recommendation,
        "total_usage": RunUsage(),
        "duration_ms": 2500,
        "is_fallback": is_fallback,
        "citation_density": 0.5,
    }
    defaults.update(kw)
    return RecommendationResult(**defaults)
