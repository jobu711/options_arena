"""Tests for section renderers in debate export.

Tests cover:
  - _render_flow_section contains all flow fields
  - _render_fundamental_section contains all fields (required and optional)
  - _render_risk_section contains risk level, PoP, mitigants
  - _render_contrarian_section contains dissent, challenge, alternative scenario
  - Full export includes all 6 agent sections + verdict
  - Export uses 'Trend Analysis' heading instead of 'Bull Case'
  - Export omits 'Bear Case' section
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from pydantic_ai.usage import RunUsage

from options_arena.agents._parsing import DebateResult
from options_arena.models import (
    AgentResponse,
    ContrarianThesis,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    MarketContext,
    RiskAssessment,
    TradeThesis,
    VolatilityThesis,
)
from options_arena.models.enums import (
    CatalystImpact,
    ExerciseStyle,
    MacdSignal,
    RiskLevel,
    SignalDirection,
    SpreadType,
)
from options_arena.reporting.debate_export import (
    _render_contrarian_section,
    _render_flow_section,
    _render_fundamental_section,
    _render_risk_section,
    export_debate_markdown,
)

# ---------------------------------------------------------------------------
# Shared fixtures — build realistic model instances
# ---------------------------------------------------------------------------


def _make_market_context() -> MarketContext:
    """Build a realistic MarketContext for AAPL."""
    return MarketContext(
        ticker="AAPL",
        current_price=Decimal("185.50"),
        price_52w_high=Decimal("199.62"),
        price_52w_low=Decimal("164.08"),
        iv_rank=45.2,
        iv_percentile=52.1,
        atm_iv_30d=28.5,
        rsi_14=62.3,
        macd_signal=MacdSignal.BULLISH_CROSSOVER,
        put_call_ratio=0.85,
        next_earnings=None,
        dte_target=45,
        target_strike=Decimal("190.00"),
        target_delta=0.35,
        sector="Information Technology",
        dividend_yield=0.005,
        exercise_style=ExerciseStyle.AMERICAN,
        data_timestamp=datetime(2026, 2, 24, 14, 30, 0, tzinfo=UTC),
    )


def _make_bull_response() -> AgentResponse:
    """Build a realistic bull AgentResponse."""
    return AgentResponse(
        agent_name="bull",
        direction=SignalDirection.BULLISH,
        confidence=0.72,
        argument="RSI at 62.3 indicates bullish momentum.",
        key_points=["RSI trending up", "Volume increasing"],
        risks_cited=["Earnings next week"],
        contracts_referenced=["AAPL $190 CALL 2026-04-10"],
        model_used="llama3.1:8b",
    )


def _make_bear_response() -> AgentResponse:
    """Build a realistic bear AgentResponse."""
    return AgentResponse(
        agent_name="bear",
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        argument="Sector rotation and earnings risk weigh on upside.",
        key_points=["Sector rotation underway"],
        risks_cited=["Strong momentum could extend"],
        contracts_referenced=["AAPL $180 PUT 2026-04-10"],
        model_used="llama3.1:8b",
    )


def _make_trade_thesis() -> TradeThesis:
    """Build a realistic TradeThesis for minimal results."""
    return TradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case supported by momentum indicators.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up", "Sector strength"],
        risk_assessment="Moderate risk. Position sizing: 2% of portfolio.",
        recommended_strategy=None,
    )


def _make_extended_thesis() -> ExtendedTradeThesis:
    """Build an ExtendedTradeThesis for full debate results."""
    return ExtendedTradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.65,
        summary="Moderate bullish case with multi-agent consensus.",
        bull_score=7.2,
        bear_score=4.5,
        key_factors=["RSI trending up", "Sector strength", "Flow confirmation"],
        risk_assessment="Moderate risk per risk agent assessment.",
        recommended_strategy=SpreadType.VERTICAL,
        agent_agreement_score=0.75,
        dissenting_agents=["contrarian"],
        agents_completed=6,
    )


def _make_flow_thesis() -> FlowThesis:
    """Build a realistic FlowThesis."""
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.70,
        gex_interpretation="Positive GEX indicates dealer hedging supports upside.",
        smart_money_signal="Institutional call buying detected on dark pools.",
        oi_analysis="Rising OI on $190 calls with bullish skew.",
        volume_confirmation="Volume 2.5x average with call-heavy flow.",
        key_flow_factors=[
            "Dark pool call buying",
            "Positive GEX regime",
            "Rising OI on near-term calls",
        ],
        model_used="llama-3.3-70b-versatile",
    )


def _make_fundamental_thesis() -> FundamentalThesis:
    """Build a realistic FundamentalThesis with all optional fields populated."""
    return FundamentalThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        catalyst_impact=CatalystImpact.MODERATE,
        earnings_assessment="Q1 earnings beat expected. Revenue growth at 12%.",
        iv_crush_risk="Moderate IV crush risk post-earnings with IV rank at 45.",
        short_interest_analysis="Short interest at 1.2% is below average.",
        dividend_impact="0.5% yield provides modest downside cushion.",
        key_fundamental_factors=[
            "Revenue growth acceleration",
            "Strong cash flow generation",
            "Services segment margin expansion",
        ],
        model_used="llama-3.3-70b-versatile",
    )


def _make_risk_assessment() -> RiskAssessment:
    """Build a realistic RiskAssessment."""
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.72,
        pop_estimate=0.42,
        max_loss_estimate="$350 per contract (premium paid)",
        charm_decay_warning="Charm decay accelerates within 14 DTE.",
        key_risks=[
            "Earnings volatility could exceed expected move",
            "Sector rotation risk if tech underperforms",
        ],
        risk_mitigants=[
            "Strong support at $180 level",
            "Buyback program limits downside",
        ],
        recommended_position_size="2% of portfolio, max 3 contracts",
        model_used="llama-3.3-70b-versatile",
    )


def _make_contrarian_thesis() -> ContrarianThesis:
    """Build a realistic ContrarianThesis."""
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.60,
        primary_challenge="Consensus ignores deteriorating breadth in tech sector.",
        overlooked_risks=[
            "Fed rate decision could trigger risk-off rotation",
            "China supply chain disruption not priced in",
        ],
        consensus_weakness="Bull case relies heavily on momentum which is mean-reverting.",
        alternative_scenario="AAPL retests $170 support if tech rotation accelerates.",
        model_used="llama-3.3-70b-versatile",
    )


def _make_volatility_thesis() -> VolatilityThesis:
    """Build a realistic VolatilityThesis."""
    return VolatilityThesis(
        iv_assessment="overpriced",
        iv_rank_interpretation="IV rank at 45 is mid-range.",
        confidence=0.65,
        recommended_strategy=SpreadType.IRON_CONDOR,
        strategy_rationale="Moderate IV favors balanced premium strategies.",
        suggested_strikes=["185C", "195C"],
        key_vol_factors=["IV rank 45", "Earnings approaching"],
        model_used="llama-3.3-70b-versatile",
    )


def _make_minimal_result() -> DebateResult:
    """Build a minimal DebateResult without optional agent responses."""
    return DebateResult(
        context=_make_market_context(),
        bull_response=_make_bull_response(),
        bear_response=_make_bear_response(),
        thesis=_make_trade_thesis(),
        total_usage=RunUsage(),
        duration_ms=1500,
        is_fallback=False,
    )


def _make_debate_result() -> DebateResult:
    """Build a complete DebateResult with all 6-agent outputs populated."""
    return DebateResult(
        context=_make_market_context(),
        bull_response=_make_bull_response(),
        bear_response=_make_bear_response(),
        thesis=_make_extended_thesis(),
        total_usage=RunUsage(),
        duration_ms=3200,
        is_fallback=False,
        vol_response=_make_volatility_thesis(),
        flow_response=_make_flow_thesis(),
        fundamental_response=_make_fundamental_thesis(),
        risk_response=_make_risk_assessment(),
        contrarian_response=_make_contrarian_thesis(),
    )


# ---------------------------------------------------------------------------
# Individual section renderer tests
# ---------------------------------------------------------------------------


def test_render_flow_section() -> None:
    """Flow section markdown contains all flow fields."""
    flow = _make_flow_thesis()
    md = _render_flow_section(flow)

    assert "## Flow Analysis" in md
    assert "Confidence: 70%" in md
    assert flow.gex_interpretation in md
    assert flow.smart_money_signal in md
    assert flow.oi_analysis in md
    assert flow.volume_confirmation in md
    for factor in flow.key_flow_factors:
        assert factor in md


def test_render_fundamental_section() -> None:
    """Fundamental section markdown contains all required and optional fields."""
    fund = _make_fundamental_thesis()
    md = _render_fundamental_section(fund)

    assert "## Fundamental Analysis" in md
    assert "Confidence: 68%" in md
    assert fund.catalyst_impact.value in md
    assert fund.earnings_assessment in md
    assert fund.iv_crush_risk in md
    # Optional fields
    assert fund.short_interest_analysis is not None
    assert fund.short_interest_analysis in md
    assert fund.dividend_impact is not None
    assert fund.dividend_impact in md
    for factor in fund.key_fundamental_factors:
        assert factor in md


def test_render_risk_section() -> None:
    """Risk section contains risk level, PoP, mitigants, and position size."""
    risk = _make_risk_assessment()
    md = _render_risk_section(risk)

    assert "## Risk Assessment" in md
    assert "Confidence: 72%" in md
    assert risk.risk_level.value in md
    assert "42%" in md  # PoP estimate
    assert risk.max_loss_estimate in md
    assert risk.charm_decay_warning is not None
    assert risk.charm_decay_warning in md
    for risk_item in risk.key_risks:
        assert risk_item in md
    for mitigant in risk.risk_mitigants:
        assert mitigant in md
    assert risk.recommended_position_size is not None
    assert risk.recommended_position_size in md


def test_render_contrarian_section() -> None:
    """Contrarian section contains dissent direction, challenge, and alt scenario."""
    contra = _make_contrarian_thesis()
    md = _render_contrarian_section(contra)

    assert "## Contrarian Challenge" in md
    assert "Confidence: 60%" in md
    assert contra.dissent_direction.value in md
    assert contra.primary_challenge in md
    assert contra.consensus_weakness in md
    assert contra.alternative_scenario in md
    for risk in contra.overlooked_risks:
        assert risk in md


# ---------------------------------------------------------------------------
# Full export tests
# ---------------------------------------------------------------------------


def test_export_includes_all_sections() -> None:
    """Export has 6 agent sections plus verdict."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    # 6 agent sections
    assert "## Trend Analysis" in md
    assert "## Flow Analysis" in md
    assert "## Fundamental Analysis" in md
    assert "## Volatility Assessment" in md
    assert "## Risk Assessment" in md
    assert "## Contrarian Challenge" in md
    # Plus verdict
    assert "## Verdict" in md


def test_export_uses_trend_heading() -> None:
    """Export uses 'Trend Analysis' heading instead of 'Bull Case'."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "## Trend Analysis" in md
    assert "## Bull Case" not in md


def test_export_omits_bear() -> None:
    """Export does not include a 'Bear Case' section."""
    result = _make_debate_result()
    md = export_debate_markdown(result)

    assert "## Bear Case" not in md
