"""Tests for build_cleaned_domain_assessment in _parsing.py.

Tests cover:
  - Think tag stripping from summary field
  - Think tag stripping from list fields (key_factors, risks)
  - Same-instance return optimization when no think tags present
  - Subclass type preservation (TrendAssessment, VolatilityAssessment)
  - Desk-specific string field cleaning (momentum_signal, etc.)
  - Non-string fields (numeric, enum, bool) remain unchanged
"""

from __future__ import annotations

from pydantic_ai import models

from options_arena.agents._parsing import build_cleaned_domain_assessment
from options_arena.models.enums import (
    DeskType,
    IVTermStructureShape,
    SignalDirection,
    VolRegime,
)
from options_arena.models.recommendation import (
    ContrarianAssessment,
    FlowAssessment,
    FundamentalAssessment,
    RiskDeskAssessment,
    TrendAssessment,
    VolatilityAssessment,
)

models.ALLOW_MODEL_REQUESTS = False

# ---------------------------------------------------------------------------
# Shared base kwargs for constructing DomainAssessment subclasses
# ---------------------------------------------------------------------------

_BASE_KWARGS: dict[str, object] = {
    "direction": SignalDirection.BULLISH,
    "confidence": 0.75,
    "summary": "Uptrend confirmed by multiple indicators.",
    "key_factors": ["Strong momentum", "Volume breakout"],
    "risks": ["Earnings approaching"],
    "contracts_referenced": ["AAPL 240C 2026-04-18"],
    "tools_used": ["fetch_quote", "compute_indicators"],
    "model_used": "llama-3.3-70b-versatile",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildCleanedDomainAssessment:
    """Tests for build_cleaned_domain_assessment generic helper."""

    def test_strips_think_tags_from_summary(self) -> None:
        """Think tags in the summary field are removed."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>reasoning here</think>Bullish momentum confirmed.",
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert "<think>" not in result.summary
        assert result.summary == "Bullish momentum confirmed."

    def test_strips_think_tags_from_list_fields(self) -> None:
        """Think tags in key_factors and risks list items are removed."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "key_factors": [
                    "<think>let me analyze</think>Strong RSI divergence",
                    "Volume increasing",
                ],
                "risks": ["<think>hmm</think>Earnings next week"],
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert result.key_factors[0] == "Strong RSI divergence"
        assert result.key_factors[1] == "Volume increasing"
        assert result.risks[0] == "Earnings next week"

    def test_no_think_tags_returns_same_instance(self) -> None:
        """When no think tags present, returns the exact same object (identity check)."""
        assessment = TrendAssessment(**_BASE_KWARGS)
        result = build_cleaned_domain_assessment(assessment)
        assert result is assessment

    def test_preserves_subclass_type_trend(self) -> None:
        """TrendAssessment in -> TrendAssessment out."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>x</think>Trend is strong.",
                "momentum_signal": "bullish crossover",
                "trend_strength": 0.85,
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, TrendAssessment)
        assert result.summary == "Trend is strong."
        assert result.momentum_signal == "bullish crossover"
        assert result.trend_strength == 0.85

    def test_preserves_subclass_type_volatility(self) -> None:
        """VolatilityAssessment in -> VolatilityAssessment out."""
        assessment = VolatilityAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>vol analysis</think>IV is elevated.",
                "iv_regime": VolRegime.ELEVATED,
                "vol_skew_assessment": "Normal skew pattern",
                "term_structure_shape": IVTermStructureShape.CONTANGO,
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, VolatilityAssessment)
        assert result.summary == "IV is elevated."
        assert result.iv_regime == VolRegime.ELEVATED
        assert result.term_structure_shape == IVTermStructureShape.CONTANGO

    def test_cleans_desk_specific_string_fields(self) -> None:
        """Desk-specific string fields like momentum_signal get cleaned."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "momentum_signal": "<think>checking</think>Bullish MACD crossover",
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, TrendAssessment)
        assert result.momentum_signal == "Bullish MACD crossover"

    def test_preserves_non_string_fields(self) -> None:
        """Numeric fields, enums, booleans are unchanged after cleaning."""
        assessment = FlowAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>flow</think>Unusual call activity.",
                "flow_bias": "bullish",
                "unusual_activity_noted": True,
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, FlowAssessment)
        assert result.confidence == 0.75
        assert result.direction == SignalDirection.BULLISH
        assert result.unusual_activity_noted is True
        assert result.desk == DeskType.FLOW
        assert result.summary == "Unusual call activity."

    def test_cleans_risk_desk_string_fields(self) -> None:
        """RiskDeskAssessment string fields are cleaned."""
        assessment = RiskDeskAssessment(
            **{
                **_BASE_KWARGS,
                "hedging_suggestion": "<think>risk check</think>Consider a put spread.",
                "portfolio_correlation_note": "<think>corr</think>Low sector correlation.",
                "max_position_pct": 0.05,
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, RiskDeskAssessment)
        assert result.hedging_suggestion == "Consider a put spread."
        assert result.portfolio_correlation_note == "Low sector correlation."
        assert result.max_position_pct == 0.05

    def test_cleans_contrarian_string_fields(self) -> None:
        """ContrarianAssessment string fields are cleaned."""
        assessment = ContrarianAssessment(
            **{
                **_BASE_KWARGS,
                "consensus_challenged": "<think>devil's advocate</think>Overconfident bulls.",
                "contrarian_thesis": "<think>alt view</think>Mean reversion likely.",
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, ContrarianAssessment)
        assert result.consensus_challenged == "Overconfident bulls."
        assert result.contrarian_thesis == "Mean reversion likely."

    def test_cleans_fundamental_string_fields(self) -> None:
        """FundamentalAssessment string fields are cleaned."""
        assessment = FundamentalAssessment(
            **{
                **_BASE_KWARGS,
                "catalyst_timeline": "<think>catalyst</think>Earnings in 14 days.",
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, FundamentalAssessment)
        assert result.catalyst_timeline == "Earnings in 14 days."

    def test_none_optional_fields_unchanged(self) -> None:
        """None optional string fields are left as None (not stripped)."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>x</think>Clean summary.",
                "momentum_signal": None,
                "trend_strength": None,
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, TrendAssessment)
        assert result.momentum_signal is None
        assert result.trend_strength is None

    def test_empty_list_fields_unchanged(self) -> None:
        """Empty list fields pass through unchanged."""
        assessment = TrendAssessment(
            **{
                **_BASE_KWARGS,
                "summary": "<think>x</think>Summary.",
                "risks": [],
                "contracts_referenced": [],
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert result.risks == []
        assert result.contracts_referenced == []

    def test_cleans_volatility_skew_assessment(self) -> None:
        """VolatilityAssessment vol_skew_assessment field is cleaned."""
        assessment = VolatilityAssessment(
            **{
                **_BASE_KWARGS,
                "vol_skew_assessment": "<think>checking skew</think>Put skew elevated.",
            },
        )
        result = build_cleaned_domain_assessment(assessment)
        assert isinstance(result, VolatilityAssessment)
        assert result.vol_skew_assessment == "Put skew elevated."
