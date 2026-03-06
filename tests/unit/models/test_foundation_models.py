"""Unit tests for DSE foundation models, enums, and config extensions.

Tests for:
  - 5 new StrEnums: MarketRegime, VolRegime, IVTermStructureShape, RiskLevel, CatalystImpact
  - FlowThesis: construction, frozen, confidence validation, key_flow_factors validation
  - RiskAssessment: construction, frozen, confidence validation, pop_estimate validation
  - FundamentalThesis: construction, frozen, confidence validation
  - ContrarianThesis: construction, frozen, dissent_confidence validation
  - ExtendedTradeThesis: construction (inherits TradeThesis), frozen, agent_agreement_score
  - DebateConfig new fields: phase1_parallelism, enable_regime_weights
  - ScanConfig new fields: enable_iv_analytics, enable_flow_analytics, etc.
"""

from enum import StrEnum

import pytest
from pydantic import ValidationError

from options_arena.models import (
    CatalystImpact,
    ContrarianThesis,
    DebateConfig,
    DimensionalScores,
    ExtendedTradeThesis,
    FlowThesis,
    FundamentalThesis,
    IVTermStructureShape,
    MarketRegime,
    RiskAssessment,
    RiskLevel,
    ScanConfig,
    SignalDirection,
    SpreadType,
    VolRegime,
)

# ---------------------------------------------------------------------------
# Helper: list of all ARENA_* env var names to clean
# ---------------------------------------------------------------------------
_ARENA_ENV_VARS = [
    "ARENA_DEBATE__PHASE1_PARALLELISM",
    "ARENA_DEBATE__ENABLE_REGIME_WEIGHTS",
    "ARENA_SCAN__ENABLE_IV_ANALYTICS",
    "ARENA_SCAN__ENABLE_FLOW_ANALYTICS",
    "ARENA_SCAN__ENABLE_FUNDAMENTAL",
    "ARENA_SCAN__ENABLE_REGIME",
]


@pytest.fixture(autouse=True)
def _clean_arena_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove DSE ARENA_* env vars before each test to prevent cross-contamination."""
    for var in _ARENA_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ===========================================================================
# New Enums
# ===========================================================================


class TestMarketRegime:
    def test_has_exactly_four_members(self) -> None:
        assert len(MarketRegime) == 4

    def test_values_are_lowercase(self) -> None:
        assert MarketRegime.TRENDING == "trending"
        assert MarketRegime.MEAN_REVERTING == "mean_reverting"
        assert MarketRegime.VOLATILE == "volatile"
        assert MarketRegime.CRISIS == "crisis"

    def test_is_str_enum(self) -> None:
        assert issubclass(MarketRegime, StrEnum)

    def test_exhaustive_iteration(self) -> None:
        assert set(MarketRegime) == {
            MarketRegime.TRENDING,
            MarketRegime.MEAN_REVERTING,
            MarketRegime.VOLATILE,
            MarketRegime.CRISIS,
        }

    def test_string_serialization(self) -> None:
        assert str(MarketRegime.TRENDING) == "trending"
        assert str(MarketRegime.MEAN_REVERTING) == "mean_reverting"
        assert str(MarketRegime.VOLATILE) == "volatile"
        assert str(MarketRegime.CRISIS) == "crisis"


class TestVolRegime:
    def test_has_exactly_four_members(self) -> None:
        assert len(VolRegime) == 4

    def test_values_are_lowercase(self) -> None:
        assert VolRegime.LOW == "low"
        assert VolRegime.NORMAL == "normal"
        assert VolRegime.ELEVATED == "elevated"
        assert VolRegime.EXTREME == "extreme"

    def test_is_str_enum(self) -> None:
        assert issubclass(VolRegime, StrEnum)

    def test_exhaustive_iteration(self) -> None:
        assert set(VolRegime) == {
            VolRegime.LOW,
            VolRegime.NORMAL,
            VolRegime.ELEVATED,
            VolRegime.EXTREME,
        }

    def test_string_serialization(self) -> None:
        assert str(VolRegime.LOW) == "low"
        assert str(VolRegime.NORMAL) == "normal"
        assert str(VolRegime.ELEVATED) == "elevated"
        assert str(VolRegime.EXTREME) == "extreme"


class TestIVTermStructureShape:
    def test_has_exactly_three_members(self) -> None:
        assert len(IVTermStructureShape) == 3

    def test_values_are_lowercase(self) -> None:
        assert IVTermStructureShape.CONTANGO == "contango"
        assert IVTermStructureShape.FLAT == "flat"
        assert IVTermStructureShape.BACKWARDATION == "backwardation"

    def test_is_str_enum(self) -> None:
        assert issubclass(IVTermStructureShape, StrEnum)

    def test_exhaustive_iteration(self) -> None:
        assert set(IVTermStructureShape) == {
            IVTermStructureShape.CONTANGO,
            IVTermStructureShape.FLAT,
            IVTermStructureShape.BACKWARDATION,
        }

    def test_string_serialization(self) -> None:
        assert str(IVTermStructureShape.CONTANGO) == "contango"
        assert str(IVTermStructureShape.FLAT) == "flat"
        assert str(IVTermStructureShape.BACKWARDATION) == "backwardation"


class TestRiskLevel:
    def test_has_exactly_four_members(self) -> None:
        assert len(RiskLevel) == 4

    def test_values_are_lowercase(self) -> None:
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MODERATE == "moderate"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.EXTREME == "extreme"

    def test_is_str_enum(self) -> None:
        assert issubclass(RiskLevel, StrEnum)

    def test_exhaustive_iteration(self) -> None:
        assert set(RiskLevel) == {
            RiskLevel.LOW,
            RiskLevel.MODERATE,
            RiskLevel.HIGH,
            RiskLevel.EXTREME,
        }

    def test_string_serialization(self) -> None:
        assert str(RiskLevel.LOW) == "low"
        assert str(RiskLevel.MODERATE) == "moderate"
        assert str(RiskLevel.HIGH) == "high"
        assert str(RiskLevel.EXTREME) == "extreme"


class TestCatalystImpact:
    def test_has_exactly_three_members(self) -> None:
        assert len(CatalystImpact) == 3

    def test_values_are_lowercase(self) -> None:
        assert CatalystImpact.LOW == "low"
        assert CatalystImpact.MODERATE == "moderate"
        assert CatalystImpact.HIGH == "high"

    def test_is_str_enum(self) -> None:
        assert issubclass(CatalystImpact, StrEnum)

    def test_exhaustive_iteration(self) -> None:
        assert set(CatalystImpact) == {
            CatalystImpact.LOW,
            CatalystImpact.MODERATE,
            CatalystImpact.HIGH,
        }

    def test_string_serialization(self) -> None:
        assert str(CatalystImpact.LOW) == "low"
        assert str(CatalystImpact.MODERATE) == "moderate"
        assert str(CatalystImpact.HIGH) == "high"


# ===========================================================================
# FlowThesis
# ===========================================================================


@pytest.fixture
def sample_flow_thesis() -> FlowThesis:
    """Create a valid FlowThesis instance for reuse."""
    return FlowThesis(
        direction=SignalDirection.BULLISH,
        confidence=0.68,
        gex_interpretation="Positive GEX suggests dealer hedging supports upside.",
        smart_money_signal="Large block trades on the ask side.",
        oi_analysis="OI concentrated at 185 strike — acts as magnet.",
        volume_confirmation="Volume 2x 20-day average on up move.",
        key_flow_factors=["Positive GEX", "Block trades on ask", "OI magnet at 185"],
        model_used="llama-3.3-70b-versatile",
    )


class TestFlowThesis:
    def test_construction(self, sample_flow_thesis: FlowThesis) -> None:
        """FlowThesis constructs with all fields correctly assigned."""
        ft = sample_flow_thesis
        assert ft.direction == SignalDirection.BULLISH
        assert ft.confidence == pytest.approx(0.68)
        assert "GEX" in ft.gex_interpretation
        assert "block" in ft.smart_money_signal.lower()
        assert "OI" in ft.oi_analysis
        assert len(ft.key_flow_factors) == 3
        assert ft.model_used == "llama-3.3-70b-versatile"

    def test_frozen(self, sample_flow_thesis: FlowThesis) -> None:
        """FlowThesis is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_flow_thesis.confidence = 0.5  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """FlowThesis rejects confidence > 1.0."""
        with pytest.raises(ValidationError, match="confidence"):
            FlowThesis(
                direction=SignalDirection.BULLISH,
                confidence=1.5,
                gex_interpretation="test",
                smart_money_signal="test",
                oi_analysis="test",
                volume_confirmation="test",
                key_flow_factors=["factor"],
                model_used="test",
            )

    def test_confidence_too_low_raises(self) -> None:
        """FlowThesis rejects confidence < 0.0."""
        with pytest.raises(ValidationError, match="confidence"):
            FlowThesis(
                direction=SignalDirection.BEARISH,
                confidence=-0.1,
                gex_interpretation="test",
                smart_money_signal="test",
                oi_analysis="test",
                volume_confirmation="test",
                key_flow_factors=["factor"],
                model_used="test",
            )

    def test_confidence_nan_raises(self) -> None:
        """FlowThesis rejects NaN confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            FlowThesis(
                direction=SignalDirection.NEUTRAL,
                confidence=float("nan"),
                gex_interpretation="test",
                smart_money_signal="test",
                oi_analysis="test",
                volume_confirmation="test",
                key_flow_factors=["factor"],
                model_used="test",
            )

    def test_confidence_inf_raises(self) -> None:
        """FlowThesis rejects Inf confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            FlowThesis(
                direction=SignalDirection.NEUTRAL,
                confidence=float("inf"),
                gex_interpretation="test",
                smart_money_signal="test",
                oi_analysis="test",
                volume_confirmation="test",
                key_flow_factors=["factor"],
                model_used="test",
            )

    def test_confidence_boundary_zero(self) -> None:
        """FlowThesis accepts confidence = 0.0."""
        ft = FlowThesis(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            gex_interpretation="test",
            smart_money_signal="test",
            oi_analysis="test",
            volume_confirmation="test",
            key_flow_factors=["factor"],
            model_used="test",
        )
        assert ft.confidence == pytest.approx(0.0)

    def test_confidence_boundary_one(self) -> None:
        """FlowThesis accepts confidence = 1.0."""
        ft = FlowThesis(
            direction=SignalDirection.BULLISH,
            confidence=1.0,
            gex_interpretation="test",
            smart_money_signal="test",
            oi_analysis="test",
            volume_confirmation="test",
            key_flow_factors=["factor"],
            model_used="test",
        )
        assert ft.confidence == pytest.approx(1.0)

    def test_empty_key_flow_factors_raises(self) -> None:
        """FlowThesis rejects empty key_flow_factors list."""
        with pytest.raises(ValidationError, match="key_flow_factors must have at least 1"):
            FlowThesis(
                direction=SignalDirection.BULLISH,
                confidence=0.5,
                gex_interpretation="test",
                smart_money_signal="test",
                oi_analysis="test",
                volume_confirmation="test",
                key_flow_factors=[],
                model_used="test",
            )

    def test_json_roundtrip(self, sample_flow_thesis: FlowThesis) -> None:
        """FlowThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_flow_thesis.model_dump_json()
        restored = FlowThesis.model_validate_json(json_str)
        assert restored == sample_flow_thesis


# ===========================================================================
# RiskAssessment
# ===========================================================================


@pytest.fixture
def sample_risk_assessment() -> RiskAssessment:
    """Create a valid RiskAssessment instance for reuse."""
    return RiskAssessment(
        risk_level=RiskLevel.MODERATE,
        confidence=0.72,
        pop_estimate=0.65,
        max_loss_estimate="$350 per contract (defined risk spread)",
        charm_decay_warning="Accelerating theta decay within 14 DTE.",
        spread_quality_assessment="Tight bid-ask spread, good fill quality.",
        key_risks=["Earnings in 7 days", "IV crush risk post-earnings"],
        risk_mitigants=["Defined risk spread", "Position sizing at 2%"],
        recommended_position_size="2% of portfolio",
        model_used="llama-3.3-70b-versatile",
    )


class TestRiskAssessment:
    def test_construction(self, sample_risk_assessment: RiskAssessment) -> None:
        """RiskAssessment constructs with all fields correctly assigned."""
        ra = sample_risk_assessment
        assert ra.risk_level == RiskLevel.MODERATE
        assert ra.confidence == pytest.approx(0.72)
        assert ra.pop_estimate == pytest.approx(0.65)
        assert "$350" in ra.max_loss_estimate
        assert ra.charm_decay_warning is not None
        assert ra.spread_quality_assessment is not None
        assert len(ra.key_risks) == 2
        assert len(ra.risk_mitigants) == 2
        assert ra.recommended_position_size == "2% of portfolio"
        assert ra.model_used == "llama-3.3-70b-versatile"

    def test_frozen(self, sample_risk_assessment: RiskAssessment) -> None:
        """RiskAssessment is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_risk_assessment.confidence = 0.5  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """RiskAssessment rejects confidence > 1.0."""
        with pytest.raises(ValidationError, match="confidence"):
            RiskAssessment(
                risk_level=RiskLevel.LOW,
                confidence=1.5,
                max_loss_estimate="test",
                key_risks=["risk"],
                risk_mitigants=[],
                model_used="test",
            )

    def test_confidence_nan_raises(self) -> None:
        """RiskAssessment rejects NaN confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            RiskAssessment(
                risk_level=RiskLevel.HIGH,
                confidence=float("nan"),
                max_loss_estimate="test",
                key_risks=["risk"],
                risk_mitigants=[],
                model_used="test",
            )

    def test_pop_estimate_too_high_raises(self) -> None:
        """RiskAssessment rejects pop_estimate > 1.0."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            RiskAssessment(
                risk_level=RiskLevel.LOW,
                confidence=0.5,
                pop_estimate=1.5,
                max_loss_estimate="test",
                key_risks=["risk"],
                risk_mitigants=[],
                model_used="test",
            )

    def test_pop_estimate_nan_raises(self) -> None:
        """RiskAssessment rejects NaN pop_estimate."""
        with pytest.raises(ValidationError, match="pop_estimate"):
            RiskAssessment(
                risk_level=RiskLevel.LOW,
                confidence=0.5,
                pop_estimate=float("nan"),
                max_loss_estimate="test",
                key_risks=["risk"],
                risk_mitigants=[],
                model_used="test",
            )

    def test_pop_estimate_none_accepted(self) -> None:
        """RiskAssessment accepts None pop_estimate."""
        ra = RiskAssessment(
            risk_level=RiskLevel.LOW,
            confidence=0.5,
            pop_estimate=None,
            max_loss_estimate="test",
            key_risks=["risk"],
            risk_mitigants=[],
            model_used="test",
        )
        assert ra.pop_estimate is None

    def test_pop_estimate_boundary_zero(self) -> None:
        """RiskAssessment accepts pop_estimate = 0.0."""
        ra = RiskAssessment(
            risk_level=RiskLevel.EXTREME,
            confidence=0.3,
            pop_estimate=0.0,
            max_loss_estimate="test",
            key_risks=["risk"],
            risk_mitigants=[],
            model_used="test",
        )
        assert ra.pop_estimate == pytest.approx(0.0)

    def test_pop_estimate_boundary_one(self) -> None:
        """RiskAssessment accepts pop_estimate = 1.0."""
        ra = RiskAssessment(
            risk_level=RiskLevel.LOW,
            confidence=0.9,
            pop_estimate=1.0,
            max_loss_estimate="test",
            key_risks=["risk"],
            risk_mitigants=[],
            model_used="test",
        )
        assert ra.pop_estimate == pytest.approx(1.0)

    def test_empty_key_risks_raises(self) -> None:
        """RiskAssessment rejects empty key_risks list."""
        with pytest.raises(ValidationError, match="key_risks must have at least 1"):
            RiskAssessment(
                risk_level=RiskLevel.LOW,
                confidence=0.5,
                max_loss_estimate="test",
                key_risks=[],
                risk_mitigants=[],
                model_used="test",
            )

    def test_optional_fields_default_none(self) -> None:
        """RiskAssessment optional fields default to None."""
        ra = RiskAssessment(
            risk_level=RiskLevel.LOW,
            confidence=0.5,
            max_loss_estimate="test",
            key_risks=["risk"],
            risk_mitigants=[],
            model_used="test",
        )
        assert ra.pop_estimate is None
        assert ra.charm_decay_warning is None
        assert ra.spread_quality_assessment is None
        assert ra.recommended_position_size is None

    def test_json_roundtrip(self, sample_risk_assessment: RiskAssessment) -> None:
        """RiskAssessment survives JSON serialization/deserialization unchanged."""
        json_str = sample_risk_assessment.model_dump_json()
        restored = RiskAssessment.model_validate_json(json_str)
        assert restored == sample_risk_assessment


# ===========================================================================
# FundamentalThesis
# ===========================================================================


@pytest.fixture
def sample_fundamental_thesis() -> FundamentalThesis:
    """Create a valid FundamentalThesis instance for reuse."""
    return FundamentalThesis(
        direction=SignalDirection.BEARISH,
        confidence=0.55,
        catalyst_impact=CatalystImpact.HIGH,
        earnings_assessment="Earnings in 5 days, high IV crush risk.",
        iv_crush_risk="Historical IV crush of 30% post-earnings.",
        short_interest_analysis="Short interest at 8.5%, elevated.",
        dividend_impact=None,
        key_fundamental_factors=["Earnings catalyst", "High IV crush risk", "Elevated SI"],
        model_used="llama-3.3-70b-versatile",
    )


class TestFundamentalThesis:
    def test_construction(self, sample_fundamental_thesis: FundamentalThesis) -> None:
        """FundamentalThesis constructs with all fields correctly assigned."""
        ft = sample_fundamental_thesis
        assert ft.direction == SignalDirection.BEARISH
        assert ft.confidence == pytest.approx(0.55)
        assert ft.catalyst_impact == CatalystImpact.HIGH
        assert "Earnings" in ft.earnings_assessment
        assert "crush" in ft.iv_crush_risk.lower()
        assert ft.short_interest_analysis is not None
        assert ft.dividend_impact is None
        assert len(ft.key_fundamental_factors) == 3
        assert ft.model_used == "llama-3.3-70b-versatile"

    def test_frozen(self, sample_fundamental_thesis: FundamentalThesis) -> None:
        """FundamentalThesis is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_fundamental_thesis.confidence = 0.5  # type: ignore[misc]

    def test_confidence_too_high_raises(self) -> None:
        """FundamentalThesis rejects confidence > 1.0."""
        with pytest.raises(ValidationError, match="confidence"):
            FundamentalThesis(
                direction=SignalDirection.BULLISH,
                confidence=1.5,
                catalyst_impact=CatalystImpact.LOW,
                earnings_assessment="test",
                iv_crush_risk="test",
                key_fundamental_factors=["factor"],
                model_used="test",
            )

    def test_confidence_nan_raises(self) -> None:
        """FundamentalThesis rejects NaN confidence."""
        with pytest.raises(ValidationError, match="confidence"):
            FundamentalThesis(
                direction=SignalDirection.BULLISH,
                confidence=float("nan"),
                catalyst_impact=CatalystImpact.LOW,
                earnings_assessment="test",
                iv_crush_risk="test",
                key_fundamental_factors=["factor"],
                model_used="test",
            )

    def test_confidence_boundary_zero(self) -> None:
        """FundamentalThesis accepts confidence = 0.0."""
        ft = FundamentalThesis(
            direction=SignalDirection.NEUTRAL,
            confidence=0.0,
            catalyst_impact=CatalystImpact.LOW,
            earnings_assessment="test",
            iv_crush_risk="test",
            key_fundamental_factors=["factor"],
            model_used="test",
        )
        assert ft.confidence == pytest.approx(0.0)

    def test_empty_key_fundamental_factors_raises(self) -> None:
        """FundamentalThesis rejects empty key_fundamental_factors list."""
        with pytest.raises(ValidationError, match="key_fundamental_factors must have at least 1"):
            FundamentalThesis(
                direction=SignalDirection.BULLISH,
                confidence=0.5,
                catalyst_impact=CatalystImpact.MODERATE,
                earnings_assessment="test",
                iv_crush_risk="test",
                key_fundamental_factors=[],
                model_used="test",
            )

    def test_json_roundtrip(self, sample_fundamental_thesis: FundamentalThesis) -> None:
        """FundamentalThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_fundamental_thesis.model_dump_json()
        restored = FundamentalThesis.model_validate_json(json_str)
        assert restored == sample_fundamental_thesis


# ===========================================================================
# ContrarianThesis
# ===========================================================================


@pytest.fixture
def sample_contrarian_thesis() -> ContrarianThesis:
    """Create a valid ContrarianThesis instance for reuse."""
    return ContrarianThesis(
        dissent_direction=SignalDirection.BEARISH,
        dissent_confidence=0.45,
        primary_challenge="Bull case ignores deteriorating breadth indicators.",
        overlooked_risks=["Sector rotation out of tech", "Rising yields"],
        consensus_weakness="Over-reliance on single RSI reading without volume confirmation.",
        alternative_scenario="If breadth continues to narrow, expect 5-8% pullback.",
        model_used="llama-3.3-70b-versatile",
    )


class TestContrarianThesis:
    def test_construction(self, sample_contrarian_thesis: ContrarianThesis) -> None:
        """ContrarianThesis constructs with all fields correctly assigned."""
        ct = sample_contrarian_thesis
        assert ct.dissent_direction == SignalDirection.BEARISH
        assert ct.dissent_confidence == pytest.approx(0.45)
        assert "breadth" in ct.primary_challenge.lower()
        assert len(ct.overlooked_risks) == 2
        assert "RSI" in ct.consensus_weakness
        assert "pullback" in ct.alternative_scenario.lower()
        assert ct.model_used == "llama-3.3-70b-versatile"

    def test_frozen(self, sample_contrarian_thesis: ContrarianThesis) -> None:
        """ContrarianThesis is frozen: attribute reassignment raises ValidationError."""
        with pytest.raises(ValidationError):
            sample_contrarian_thesis.dissent_confidence = 0.5  # type: ignore[misc]

    def test_dissent_confidence_too_high_raises(self) -> None:
        """ContrarianThesis rejects dissent_confidence > 1.0."""
        with pytest.raises(ValidationError, match="dissent_confidence"):
            ContrarianThesis(
                dissent_direction=SignalDirection.BEARISH,
                dissent_confidence=1.5,
                primary_challenge="test",
                overlooked_risks=["risk"],
                consensus_weakness="test",
                alternative_scenario="test",
                model_used="test",
            )

    def test_dissent_confidence_too_low_raises(self) -> None:
        """ContrarianThesis rejects dissent_confidence < 0.0."""
        with pytest.raises(ValidationError, match="dissent_confidence"):
            ContrarianThesis(
                dissent_direction=SignalDirection.BULLISH,
                dissent_confidence=-0.1,
                primary_challenge="test",
                overlooked_risks=["risk"],
                consensus_weakness="test",
                alternative_scenario="test",
                model_used="test",
            )

    def test_dissent_confidence_nan_raises(self) -> None:
        """ContrarianThesis rejects NaN dissent_confidence."""
        with pytest.raises(ValidationError, match="dissent_confidence"):
            ContrarianThesis(
                dissent_direction=SignalDirection.NEUTRAL,
                dissent_confidence=float("nan"),
                primary_challenge="test",
                overlooked_risks=["risk"],
                consensus_weakness="test",
                alternative_scenario="test",
                model_used="test",
            )

    def test_dissent_confidence_inf_raises(self) -> None:
        """ContrarianThesis rejects Inf dissent_confidence."""
        with pytest.raises(ValidationError, match="dissent_confidence"):
            ContrarianThesis(
                dissent_direction=SignalDirection.NEUTRAL,
                dissent_confidence=float("inf"),
                primary_challenge="test",
                overlooked_risks=["risk"],
                consensus_weakness="test",
                alternative_scenario="test",
                model_used="test",
            )

    def test_dissent_confidence_boundary_zero(self) -> None:
        """ContrarianThesis accepts dissent_confidence = 0.0."""
        ct = ContrarianThesis(
            dissent_direction=SignalDirection.NEUTRAL,
            dissent_confidence=0.0,
            primary_challenge="test",
            overlooked_risks=["risk"],
            consensus_weakness="test",
            alternative_scenario="test",
            model_used="test",
        )
        assert ct.dissent_confidence == pytest.approx(0.0)

    def test_dissent_confidence_boundary_one(self) -> None:
        """ContrarianThesis accepts dissent_confidence = 1.0."""
        ct = ContrarianThesis(
            dissent_direction=SignalDirection.BEARISH,
            dissent_confidence=1.0,
            primary_challenge="test",
            overlooked_risks=["risk"],
            consensus_weakness="test",
            alternative_scenario="test",
            model_used="test",
        )
        assert ct.dissent_confidence == pytest.approx(1.0)

    def test_empty_overlooked_risks_raises(self) -> None:
        """ContrarianThesis rejects empty overlooked_risks list."""
        with pytest.raises(ValidationError, match="overlooked_risks must have at least 1"):
            ContrarianThesis(
                dissent_direction=SignalDirection.BEARISH,
                dissent_confidence=0.5,
                primary_challenge="test",
                overlooked_risks=[],
                consensus_weakness="test",
                alternative_scenario="test",
                model_used="test",
            )

    def test_json_roundtrip(self, sample_contrarian_thesis: ContrarianThesis) -> None:
        """ContrarianThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_contrarian_thesis.model_dump_json()
        restored = ContrarianThesis.model_validate_json(json_str)
        assert restored == sample_contrarian_thesis


# ===========================================================================
# ExtendedTradeThesis
# ===========================================================================


@pytest.fixture
def sample_extended_trade_thesis() -> ExtendedTradeThesis:
    """Create a valid ExtendedTradeThesis instance for reuse."""
    return ExtendedTradeThesis(
        ticker="AAPL",
        direction=SignalDirection.BULLISH,
        confidence=0.75,
        summary="Strong bull case with flow confirmation.",
        bull_score=7.5,
        bear_score=4.0,
        key_factors=["RSI oversold", "Positive GEX", "Flow confirmation"],
        risk_assessment="Moderate risk due to earnings proximity.",
        recommended_strategy=SpreadType.VERTICAL,
        contrarian_dissent="Breadth indicators suggest caution.",
        agent_agreement_score=0.80,
        dissenting_agents=["contrarian"],
        dimensional_scores=DimensionalScores(
            trend=72.5,
            iv_vol=65.0,
            flow=80.0,
        ),
        agents_completed=5,
    )


class TestExtendedTradeThesis:
    def test_construction(self, sample_extended_trade_thesis: ExtendedTradeThesis) -> None:
        """ExtendedTradeThesis constructs with all fields including inherited ones."""
        ett = sample_extended_trade_thesis
        # Inherited fields from TradeThesis
        assert ett.ticker == "AAPL"
        assert ett.direction == SignalDirection.BULLISH
        assert ett.confidence == pytest.approx(0.75)
        assert ett.bull_score == pytest.approx(7.5)
        assert ett.bear_score == pytest.approx(4.0)
        assert len(ett.key_factors) == 3
        assert ett.recommended_strategy == SpreadType.VERTICAL
        # New DSE fields
        assert ett.contrarian_dissent == "Breadth indicators suggest caution."
        assert ett.agent_agreement_score == pytest.approx(0.80)
        assert ett.dissenting_agents == ["contrarian"]
        assert ett.dimensional_scores is not None
        assert ett.dimensional_scores.trend == pytest.approx(72.5)
        assert ett.agents_completed == 5

    def test_frozen(self, sample_extended_trade_thesis: ExtendedTradeThesis) -> None:
        """ExtendedTradeThesis is frozen (inherited from TradeThesis)."""
        with pytest.raises(ValidationError):
            sample_extended_trade_thesis.ticker = "MSFT"  # type: ignore[misc]

    def test_defaults(self) -> None:
        """ExtendedTradeThesis DSE fields have correct defaults."""
        ett = ExtendedTradeThesis(
            ticker="MSFT",
            direction=SignalDirection.NEUTRAL,
            confidence=0.5,
            summary="Neutral outlook.",
            bull_score=5.0,
            bear_score=5.0,
            key_factors=["mixed signals"],
            risk_assessment="Moderate risk.",
        )
        assert ett.contrarian_dissent is None
        assert ett.agent_agreement_score is None
        assert ett.dissenting_agents == []
        assert ett.dimensional_scores is None
        assert ett.agents_completed == 0

    def test_agent_agreement_score_too_high_raises(self) -> None:
        """ExtendedTradeThesis rejects agent_agreement_score > 1.0."""
        with pytest.raises(ValidationError, match="agent_agreement_score"):
            ExtendedTradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.7,
                summary="test",
                bull_score=7.0,
                bear_score=4.0,
                key_factors=["factor"],
                risk_assessment="test",
                agent_agreement_score=1.5,
            )

    def test_agent_agreement_score_nan_raises(self) -> None:
        """ExtendedTradeThesis rejects NaN agent_agreement_score."""
        with pytest.raises(ValidationError, match="agent_agreement_score"):
            ExtendedTradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.7,
                summary="test",
                bull_score=7.0,
                bear_score=4.0,
                key_factors=["factor"],
                risk_assessment="test",
                agent_agreement_score=float("nan"),
            )

    def test_agent_agreement_score_none_accepted(self) -> None:
        """ExtendedTradeThesis accepts None agent_agreement_score."""
        ett = ExtendedTradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            summary="test",
            bull_score=7.0,
            bear_score=4.0,
            key_factors=["factor"],
            risk_assessment="test",
            agent_agreement_score=None,
        )
        assert ett.agent_agreement_score is None

    def test_agent_agreement_score_boundary_zero(self) -> None:
        """ExtendedTradeThesis accepts agent_agreement_score = 0.0."""
        ett = ExtendedTradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            summary="test",
            bull_score=7.0,
            bear_score=4.0,
            key_factors=["factor"],
            risk_assessment="test",
            agent_agreement_score=0.0,
        )
        assert ett.agent_agreement_score == pytest.approx(0.0)

    def test_agent_agreement_score_boundary_one(self) -> None:
        """ExtendedTradeThesis accepts agent_agreement_score = 1.0."""
        ett = ExtendedTradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BULLISH,
            confidence=0.7,
            summary="test",
            bull_score=7.0,
            bear_score=4.0,
            key_factors=["factor"],
            risk_assessment="test",
            agent_agreement_score=1.0,
        )
        assert ett.agent_agreement_score == pytest.approx(1.0)

    def test_agents_completed_negative_raises(self) -> None:
        """ExtendedTradeThesis rejects negative agents_completed."""
        with pytest.raises(ValidationError, match="agents_completed"):
            ExtendedTradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.7,
                summary="test",
                bull_score=7.0,
                bear_score=4.0,
                key_factors=["factor"],
                risk_assessment="test",
                agents_completed=-1,
            )

    def test_agents_completed_too_high_raises(self) -> None:
        """ExtendedTradeThesis rejects agents_completed > 20."""
        with pytest.raises(ValidationError, match="agents_completed"):
            ExtendedTradeThesis(
                ticker="AAPL",
                direction=SignalDirection.BULLISH,
                confidence=0.7,
                summary="test",
                bull_score=7.0,
                bear_score=4.0,
                key_factors=["factor"],
                risk_assessment="test",
                agents_completed=21,
            )

    def test_inherits_confidence_clamping(self) -> None:
        """ExtendedTradeThesis inherits score-confidence clamping from TradeThesis."""
        ett = ExtendedTradeThesis(
            ticker="AAPL",
            direction=SignalDirection.BEARISH,
            confidence=0.8,
            summary="Contradictory.",
            bull_score=7.0,
            bear_score=4.0,
            key_factors=["mismatch"],
            risk_assessment="High risk.",
        )
        # Clamped because bull_score > bear_score but direction is BEARISH
        assert ett.confidence == pytest.approx(0.5)

    def test_json_roundtrip(self, sample_extended_trade_thesis: ExtendedTradeThesis) -> None:
        """ExtendedTradeThesis survives JSON serialization/deserialization unchanged."""
        json_str = sample_extended_trade_thesis.model_dump_json()
        restored = ExtendedTradeThesis.model_validate_json(json_str)
        assert restored == sample_extended_trade_thesis


# ===========================================================================
# Config Extensions
# ===========================================================================


class TestDebateConfigDSEFields:
    """Tests for new DebateConfig fields: phase1_parallelism, enable_regime_weights."""

    def test_phase1_parallelism_default(self) -> None:
        """Default phase1_parallelism is 2 (free tier optimized)."""
        config = DebateConfig()
        assert config.phase1_parallelism == 2

    def test_enable_regime_weights_default(self) -> None:
        """Default enable_regime_weights is False."""
        config = DebateConfig()
        assert config.enable_regime_weights is False

    def test_phase1_parallelism_valid_range(self) -> None:
        """phase1_parallelism accepts values in [1, 8]."""
        config_low = DebateConfig(phase1_parallelism=1)
        assert config_low.phase1_parallelism == 1
        config_high = DebateConfig(phase1_parallelism=8)
        assert config_high.phase1_parallelism == 8

    def test_phase1_parallelism_below_1_raises(self) -> None:
        """phase1_parallelism below 1 is rejected."""
        with pytest.raises(ValidationError, match="phase1_parallelism must be in"):
            DebateConfig(phase1_parallelism=0)

    def test_phase1_parallelism_above_8_raises(self) -> None:
        """phase1_parallelism above 8 is rejected."""
        with pytest.raises(ValidationError, match="phase1_parallelism must be in"):
            DebateConfig(phase1_parallelism=9)

    def test_enable_regime_weights_true(self) -> None:
        """enable_regime_weights can be set to True."""
        config = DebateConfig(enable_regime_weights=True)
        assert config.enable_regime_weights is True


class TestScanConfigDSEFields:
    """Tests for new ScanConfig fields: enable_iv_analytics, etc."""

    def test_enable_iv_analytics_default(self) -> None:
        """Default enable_iv_analytics is True."""
        config = ScanConfig()
        assert config.enable_iv_analytics is True

    def test_enable_flow_analytics_default(self) -> None:
        """Default enable_flow_analytics is True."""
        config = ScanConfig()
        assert config.enable_flow_analytics is True

    def test_enable_fundamental_default(self) -> None:
        """Default enable_fundamental is True."""
        config = ScanConfig()
        assert config.enable_fundamental is True

    def test_enable_regime_default(self) -> None:
        """Default enable_regime is True."""
        config = ScanConfig()
        assert config.enable_regime is True

    def test_disable_iv_analytics(self) -> None:
        """enable_iv_analytics can be set to False."""
        config = ScanConfig(enable_iv_analytics=False)
        assert config.enable_iv_analytics is False

    def test_disable_flow_analytics(self) -> None:
        """enable_flow_analytics can be set to False."""
        config = ScanConfig(enable_flow_analytics=False)
        assert config.enable_flow_analytics is False

    def test_disable_fundamental(self) -> None:
        """enable_fundamental can be set to False."""
        config = ScanConfig(enable_fundamental=False)
        assert config.enable_fundamental is False

    def test_disable_regime(self) -> None:
        """enable_regime can be set to False."""
        config = ScanConfig(enable_regime=False)
        assert config.enable_regime is False
