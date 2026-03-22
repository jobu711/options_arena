"""Tests for recommendation export — markdown rendering of RecommendationResult.

Tests cover:
  - Basic export contains key sections (header, recommendation, assessments)
  - All 6 domain assessments rendered with desk names
  - Decimal precision preserved (2dp, no float conversion)
  - Fallback badge appears when is_fallback=True
  - Direction displayed in output
  - Empty assessments list handled gracefully
  - Desk-specific fields rendered when populated
  - None optional fields on PositionRecommendation gracefully skipped
"""

from __future__ import annotations

from decimal import Decimal

from pydantic_ai.usage import RunUsage

from options_arena.models.enums import (
    DeskType,
    IVTermStructureShape,
    SignalDirection,
    SpreadType,
    ValuationSignal,
    VolRegime,
)
from options_arena.models.recommendation import (
    ContrarianAssessment,
    FlowAssessment,
    FundamentalAssessment,
    PositionRecommendation,
    RecommendationResult,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)
from options_arena.reporting.debate_export import (
    _render_assessment_section,
    _render_recommendation_section,
    export_recommendation_markdown,
)
from tests.factories import make_market_context

# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_position_recommendation(**kw: object) -> PositionRecommendation:
    """Build a test PositionRecommendation with sensible defaults."""
    defaults: dict[str, object] = {
        "ticker": "AAPL",
        "direction": SignalDirection.BULLISH,
        "confidence": 0.75,
        "recommended_contract": "AAPL 190C 2026-04-18",
        "entry_price": Decimal("5.50"),
        "entry_criteria": "Enter on pullback to $184 support",
        "exit_criteria": "Exit at target or if RSI drops below 30",
        "stop_loss": Decimal("3.25"),
        "take_profit": Decimal("8.75"),
        "position_size_pct": 0.05,
        "position_rationale": "5% position appropriate for moderate conviction",
        "risk_reward_ratio": 1.44,
        "max_loss_estimate": "$550 per contract (full premium)",
        "recommended_strategy": SpreadType.VERTICAL,
        "strategy_rationale": "Vertical spread limits downside",
        "summary": "Bullish outlook supported by strong momentum.",
        "key_factors": ["RSI above 60", "SMA alignment bullish", "Volume confirmation"],
        "risk_assessment": "Moderate risk due to earnings in 30 days.",
        "agent_agreement_score": 0.83,
        "dissenting_desks": [DeskType.CONTRARIAN],
        "model_used": "llama-3.3-70b-versatile",
    }
    defaults.update(kw)
    return PositionRecommendation(**defaults)


def _make_trend_assessment(**kw: object) -> TrendAssessment:
    """Build a test TrendAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.TREND,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.80,
        "summary": "Strong uptrend with momentum confirmation.",
        "key_factors": ["SMA alignment bullish", "ADX above 25"],
        "risks": ["Potential exhaustion near resistance"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_price_history", "compute_indicators"],
        "model_used": "llama-3.3-70b-versatile",
        "trend_strength": 0.85,
        "momentum_signal": "Strong bullish",
    }
    defaults.update(kw)
    return TrendAssessment(**defaults)


def _make_volatility_assessment(**kw: object) -> VolatilityAssessment:
    """Build a test VolatilityAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.VOLATILITY,
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.65,
        "summary": "IV is elevated but not extreme.",
        "key_factors": ["IV rank at 60th percentile"],
        "risks": ["IV crush risk post-earnings"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_iv_surface"],
        "model_used": "llama-3.3-70b-versatile",
        "iv_regime": VolRegime.ELEVATED,
        "vol_skew_assessment": "Moderate put skew",
        "term_structure_shape": IVTermStructureShape.CONTANGO,
    }
    defaults.update(kw)
    return VolatilityAssessment(**defaults)


def _make_flow_assessment(**kw: object) -> FlowAssessment:
    """Build a test FlowAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.FLOW,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.70,
        "summary": "Bullish flow bias with unusual call activity.",
        "key_factors": ["Large call sweeps detected"],
        "risks": ["Possible hedging activity"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_options_flow"],
        "model_used": "llama-3.3-70b-versatile",
        "flow_bias": "Net bullish",
        "unusual_activity_noted": True,
    }
    defaults.update(kw)
    return FlowAssessment(**defaults)


def _make_fundamental_assessment(**kw: object) -> FundamentalAssessment:
    """Build a test FundamentalAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.FUNDAMENTAL,
        "direction": SignalDirection.BULLISH,
        "confidence": 0.60,
        "summary": "Undervalued with upcoming catalyst.",
        "key_factors": ["P/E below sector average"],
        "risks": ["Revenue guidance uncertain"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["fetch_fundamentals"],
        "model_used": "llama-3.3-70b-versatile",
        "valuation_signal": ValuationSignal.UNDERVALUED,
        "catalyst_timeline": "Earnings in 14 days",
    }
    defaults.update(kw)
    return FundamentalAssessment(**defaults)


def _make_risk_assessment(**kw: object) -> RiskDeskAssessment:
    """Build a test RiskDeskAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.RISK,
        "direction": SignalDirection.NEUTRAL,
        "confidence": 0.70,
        "summary": "Moderate risk profile, position sizing adjusted.",
        "key_factors": ["Earnings proximity adds tail risk"],
        "risks": ["Gap risk on earnings miss"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"],
        "tools_used": ["compute_position_size"],
        "model_used": "llama-3.3-70b-versatile",
        "max_position_pct": 0.05,
        "hedging_suggestion": "Consider protective put",
        "portfolio_correlation_note": "Low correlation with existing holdings",
    }
    defaults.update(kw)
    return RiskDeskAssessment(**defaults)


def _make_contrarian_assessment(**kw: object) -> ContrarianAssessment:
    """Build a test ContrarianAssessment."""
    defaults: dict[str, object] = {
        "desk": DeskType.CONTRARIAN,
        "direction": SignalDirection.BEARISH,
        "confidence": 0.55,
        "summary": "Crowded trade with sentiment at extreme.",
        "key_factors": ["Consensus too bullish"],
        "risks": ["Mean reversion overdue"],
        "contracts_referenced": ["AAPL 185P 2026-04-18"],
        "tools_used": ["fetch_sentiment"],
        "model_used": "llama-3.3-70b-versatile",
        "consensus_challenged": "Bullish consensus overly optimistic",
        "contrarian_thesis": "Likely pullback after extended run",
    }
    defaults.update(kw)
    return ContrarianAssessment(**defaults)


def _make_all_assessments() -> list[
    TrendAssessment
    | VolatilityAssessment
    | FlowAssessment
    | FundamentalAssessment
    | RiskDeskAssessment
    | ContrarianAssessment
]:
    """Build all 6 domain assessments."""
    return [
        _make_trend_assessment(),
        _make_volatility_assessment(),
        _make_flow_assessment(),
        _make_fundamental_assessment(),
        _make_risk_assessment(),
        _make_contrarian_assessment(),
    ]


def _make_recommendation_result(**kw: object) -> RecommendationResult:
    """Build a test RecommendationResult with all 6 assessments."""
    defaults: dict[str, object] = {
        "context": make_market_context(),
        "assessments": _make_all_assessments(),
        "recommendation": _make_position_recommendation(),
        "total_usage": RunUsage(),
        "duration_ms": 3500,
        "is_fallback": False,
        "citation_density": 0.45,
    }
    defaults.update(kw)
    return RecommendationResult(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderAssessmentSection:
    """Tests for _render_assessment_section helper."""

    def test_renders_desk_name_and_confidence(self) -> None:
        """Verify desk name appears as heading with confidence."""
        assessment = _make_trend_assessment()
        md = _render_assessment_section(assessment)
        assert "### Trend (Confidence: 80%)" in md

    def test_renders_direction(self) -> None:
        """Verify direction is displayed."""
        assessment = _make_trend_assessment(direction=SignalDirection.BEARISH)
        md = _render_assessment_section(assessment)
        assert "Bearish" in md

    def test_renders_summary(self) -> None:
        """Verify summary paragraph appears."""
        assessment = _make_trend_assessment(summary="Custom summary text here.")
        md = _render_assessment_section(assessment)
        assert "Custom summary text here." in md

    def test_renders_key_factors(self) -> None:
        """Verify key factors rendered as bullet list."""
        assessment = _make_trend_assessment(key_factors=["Factor A", "Factor B"])
        md = _render_assessment_section(assessment)
        assert "- Factor A" in md
        assert "- Factor B" in md

    def test_renders_risks(self) -> None:
        """Verify risks rendered as bullet list."""
        assessment = _make_risk_assessment(risks=["Risk X", "Risk Y"])
        md = _render_assessment_section(assessment)
        assert "- Risk X" in md
        assert "- Risk Y" in md

    def test_trend_specific_fields(self) -> None:
        """Verify trend-specific fields appear."""
        assessment = _make_trend_assessment(trend_strength=0.85, momentum_signal="Strong bullish")
        md = _render_assessment_section(assessment)
        assert "Trend Strength" in md
        assert "0.85" in md
        assert "Momentum Signal" in md
        assert "Strong bullish" in md

    def test_volatility_specific_fields(self) -> None:
        """Verify volatility-specific fields appear."""
        assessment = _make_volatility_assessment(
            iv_regime=VolRegime.ELEVATED,
            term_structure_shape=IVTermStructureShape.CONTANGO,
        )
        md = _render_assessment_section(assessment)
        assert "IV Regime" in md
        assert "elevated" in md
        assert "Term Structure" in md
        assert "contango" in md

    def test_flow_specific_fields(self) -> None:
        """Verify flow-specific fields appear."""
        assessment = _make_flow_assessment(flow_bias="Net bullish", unusual_activity_noted=True)
        md = _render_assessment_section(assessment)
        assert "Flow Bias" in md
        assert "Net bullish" in md
        assert "Unusual Activity" in md

    def test_fundamental_specific_fields(self) -> None:
        """Verify fundamental-specific fields appear."""
        assessment = _make_fundamental_assessment(
            valuation_signal=ValuationSignal.UNDERVALUED,
            catalyst_timeline="Earnings in 14 days",
        )
        md = _render_assessment_section(assessment)
        assert "Valuation Signal" in md
        assert "undervalued" in md
        assert "Catalyst Timeline" in md

    def test_risk_specific_fields(self) -> None:
        """Verify risk-specific fields appear."""
        assessment = _make_risk_assessment(
            max_position_pct=0.05,
            hedging_suggestion="Consider protective put",
        )
        md = _render_assessment_section(assessment)
        assert "Max Position" in md
        assert "5%" in md
        assert "Hedging Suggestion" in md

    def test_contrarian_specific_fields(self) -> None:
        """Verify contrarian-specific fields appear."""
        assessment = _make_contrarian_assessment(
            consensus_challenged="Too bullish",
            contrarian_thesis="Pullback likely",
        )
        md = _render_assessment_section(assessment)
        assert "Consensus Challenged" in md
        assert "Too bullish" in md
        assert "Contrarian Thesis" in md

    def test_none_optional_fields_skipped(self) -> None:
        """Verify None optional fields do not appear."""
        assessment = _make_trend_assessment(trend_strength=None, momentum_signal=None)
        md = _render_assessment_section(assessment)
        assert "Trend Strength" not in md
        assert "Momentum Signal" not in md


class TestRenderRecommendationSection:
    """Tests for _render_recommendation_section helper."""

    def test_renders_contract_details(self) -> None:
        """Verify contract info appears."""
        rec = _make_position_recommendation()
        md = _render_recommendation_section(rec)
        assert "AAPL 190C 2026-04-18" in md

    def test_renders_entry_price_with_decimal_precision(self) -> None:
        """Verify Decimal entry price rendered with 2dp."""
        rec = _make_position_recommendation(entry_price=Decimal("5.50"))
        md = _render_recommendation_section(rec)
        assert "5.50" in md

    def test_renders_stop_loss_with_decimal_precision(self) -> None:
        """Verify Decimal stop loss rendered with 2dp."""
        rec = _make_position_recommendation(stop_loss=Decimal("3.25"))
        md = _render_recommendation_section(rec)
        assert "3.25" in md

    def test_renders_take_profit_with_decimal_precision(self) -> None:
        """Verify Decimal take profit rendered with 2dp."""
        rec = _make_position_recommendation(take_profit=Decimal("8.75"))
        md = _render_recommendation_section(rec)
        assert "8.75" in md

    def test_none_stop_loss_skipped(self) -> None:
        """Verify None stop_loss row is omitted."""
        rec = _make_position_recommendation(stop_loss=None)
        md = _render_recommendation_section(rec)
        assert "Stop Loss" not in md

    def test_none_take_profit_skipped(self) -> None:
        """Verify None take_profit row is omitted."""
        rec = _make_position_recommendation(take_profit=None)
        md = _render_recommendation_section(rec)
        assert "Take Profit" not in md

    def test_renders_position_size(self) -> None:
        """Verify position size percentage is shown."""
        rec = _make_position_recommendation(position_size_pct=0.05)
        md = _render_recommendation_section(rec)
        assert "5%" in md

    def test_renders_risk_reward(self) -> None:
        """Verify risk/reward ratio is shown."""
        rec = _make_position_recommendation(risk_reward_ratio=1.44)
        md = _render_recommendation_section(rec)
        assert "1.44" in md

    def test_renders_agent_agreement(self) -> None:
        """Verify agent agreement score is shown."""
        rec = _make_position_recommendation(agent_agreement_score=0.83)
        md = _render_recommendation_section(rec)
        assert "Agent Agreement" in md
        assert "83%" in md

    def test_renders_dissenting_desks(self) -> None:
        """Verify dissenting desks are listed."""
        rec = _make_position_recommendation(dissenting_desks=[DeskType.CONTRARIAN, DeskType.RISK])
        md = _render_recommendation_section(rec)
        assert "Dissenting Desks" in md
        assert "Contrarian" in md
        assert "Risk" in md

    def test_no_agent_agreement_when_none(self) -> None:
        """Verify agent agreement section omitted when None."""
        rec = _make_position_recommendation(agent_agreement_score=None)
        md = _render_recommendation_section(rec)
        assert "Agent Agreement" not in md

    def test_no_dissenting_when_empty(self) -> None:
        """Verify dissenting desks section omitted when empty."""
        rec = _make_position_recommendation(dissenting_desks=[])
        md = _render_recommendation_section(rec)
        assert "Dissenting Desks" not in md


class TestExportRecommendationMarkdown:
    """Tests for the main export_recommendation_markdown function."""

    def test_basic_export(self) -> None:
        """Verify markdown export contains key sections."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        assert "## Position Recommendation" in md
        assert "## Domain Assessments" in md
        assert "# Options Arena Recommendation Report: AAPL" in md

    def test_all_assessments_rendered(self) -> None:
        """Verify all 6 domain assessments appear in output."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        for desk in ["Trend", "Volatility", "Flow", "Fundamental", "Risk", "Contrarian"]:
            assert desk in md

    def test_decimal_precision_preserved(self) -> None:
        """Verify Decimal fields rendered with 2 decimal places."""
        result = _make_recommendation_result(
            recommendation=_make_position_recommendation(
                entry_price=Decimal("5.50"),
                stop_loss=Decimal("3.25"),
                take_profit=Decimal("8.75"),
            )
        )
        md = export_recommendation_markdown(result)
        assert "5.50" in md
        assert "3.25" in md
        assert "8.75" in md

    def test_fallback_badge(self) -> None:
        """Verify fallback indicator appears when is_fallback=True."""
        result = _make_recommendation_result(is_fallback=True)
        md = export_recommendation_markdown(result)
        assert "Fallback" in md
        assert "Data-Driven Fallback" in md
        assert "**Fallback**: Yes" in md

    def test_no_fallback_badge_when_false(self) -> None:
        """Verify no fallback badge when is_fallback=False."""
        result = _make_recommendation_result(is_fallback=False)
        md = export_recommendation_markdown(result)
        assert "**Fallback**: No" in md
        assert "Data-Driven Fallback" not in md

    def test_direction_displayed(self) -> None:
        """Verify direction (BULLISH/BEARISH/NEUTRAL) is shown."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        assert "Bullish" in md

    def test_empty_assessments_handled(self) -> None:
        """Verify graceful handling when assessments list is empty."""
        result = _make_recommendation_result(assessments=[])
        md = export_recommendation_markdown(result)
        assert "No assessments available" in md
        assert "## Position Recommendation" in md

    def test_market_snapshot_present(self) -> None:
        """Verify market snapshot section is included."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        assert "## Market Snapshot" in md

    def test_header_contains_ticker(self) -> None:
        """Verify report header contains the ticker symbol."""
        result = _make_recommendation_result(
            recommendation=_make_position_recommendation(ticker="MSFT")
        )
        md = export_recommendation_markdown(result)
        assert "MSFT" in md

    def test_header_contains_duration(self) -> None:
        """Verify header shows duration in seconds."""
        result = _make_recommendation_result(duration_ms=5000)
        md = export_recommendation_markdown(result)
        assert "5.0s" in md

    def test_header_contains_model(self) -> None:
        """Verify header shows model name."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        assert "llama-3.3-70b-versatile" in md

    def test_bearish_direction_displayed(self) -> None:
        """Verify bearish direction renders correctly."""
        result = _make_recommendation_result(
            recommendation=_make_position_recommendation(
                direction=SignalDirection.BEARISH,
                confidence=0.30,
            )
        )
        md = export_recommendation_markdown(result)
        assert "Bearish" in md

    def test_re_export_from_package(self) -> None:
        """Verify function is importable from the reporting package."""
        from options_arena.reporting import export_recommendation_markdown as fn

        assert callable(fn)

    def test_output_is_string(self) -> None:
        """Verify return type is str."""
        result = _make_recommendation_result()
        md = export_recommendation_markdown(result)
        assert isinstance(md, str)

    def test_decimal_not_float_converted(self) -> None:
        """Verify Decimal fields survive without float precision issues.

        Decimal("5.50") should appear as "5.50", not "5.5" or
        "5.500000000000000222..."
        """
        rec = _make_position_recommendation(entry_price=Decimal("5.50"))
        result = _make_recommendation_result(recommendation=rec)
        md = export_recommendation_markdown(result)
        # Check the exact 2dp format appears
        assert "$5.50" in md

    def test_low_confidence_fallback(self) -> None:
        """Verify low confidence + fallback renders correctly."""
        rec = _make_position_recommendation(confidence=0.20)
        result = _make_recommendation_result(
            recommendation=rec,
            is_fallback=True,
        )
        md = export_recommendation_markdown(result)
        assert "20%" in md
        assert "Data-Driven Fallback" in md
