"""Options Arena — Recommendation models for unified agent system.

DomainAssessment hierarchy with 6 desk-specific subclasses and discriminated
union for polymorphic JSON round-trip. PositionRecommendation and
RecommendationResult wrap the full recommendation pipeline output.
All models are frozen snapshots.
"""

import math
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_serializer,
    field_validator,
)
from pydantic_ai.usage import RunUsage

from options_arena.models._validators import validate_non_empty_list, validate_unit_interval
from options_arena.models.analysis import MarketContext
from options_arena.models.enums import (
    DeskType,
    IVTermStructureShape,
    SignalDirection,
    SpreadType,
    ValuationSignal,
    VolRegime,
)


class DomainAssessment(BaseModel):
    """Base assessment produced by a single desk agent."""

    model_config = ConfigDict(frozen=True)

    desk: DeskType
    direction: SignalDirection
    confidence: float
    summary: str
    key_factors: list[str]
    risks: list[str]
    contracts_referenced: list[str]
    tools_used: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        return validate_unit_interval(v, "confidence")

    @field_validator("key_factors")
    @classmethod
    def _validate_key_factors(cls, v: list[str]) -> list[str]:
        return validate_non_empty_list(v, "key_factors")


# ---------------------------------------------------------------------------
# Desk-specific subclasses
# ---------------------------------------------------------------------------


class TrendAssessment(DomainAssessment):
    """Trend desk assessment with momentum-specific fields."""

    desk: Literal[DeskType.TREND] = DeskType.TREND
    trend_strength: float | None = None
    momentum_signal: str | None = None

    @field_validator("trend_strength")
    @classmethod
    def _validate_trend_strength(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError(f"trend_strength must be finite, got {v}")
        return v


class VolatilityAssessment(DomainAssessment):
    """Volatility desk assessment with IV regime and term structure."""

    desk: Literal[DeskType.VOLATILITY] = DeskType.VOLATILITY
    iv_regime: VolRegime | None = None
    vol_skew_assessment: str | None = None
    term_structure_shape: IVTermStructureShape | None = None


class FlowAssessment(DomainAssessment):
    """Flow desk assessment with order flow bias."""

    desk: Literal[DeskType.FLOW] = DeskType.FLOW
    flow_bias: str | None = None
    unusual_activity_noted: bool = False


class FundamentalAssessment(DomainAssessment):
    """Fundamental desk assessment with valuation signal and catalyst."""

    desk: Literal[DeskType.FUNDAMENTAL] = DeskType.FUNDAMENTAL
    valuation_signal: ValuationSignal | None = None
    catalyst_timeline: str | None = None


class RiskDeskAssessment(DomainAssessment):
    """Risk desk assessment with position sizing and hedging."""

    desk: Literal[DeskType.RISK] = DeskType.RISK
    max_position_pct: float | None = None
    hedging_suggestion: str | None = None
    portfolio_correlation_note: str | None = None

    @field_validator("max_position_pct")
    @classmethod
    def _validate_max_position_pct(cls, v: float | None) -> float | None:
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"max_position_pct must be finite, got {v}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"max_position_pct must be in [0, 1], got {v}")
        return v


class ContrarianAssessment(DomainAssessment):
    """Contrarian desk assessment challenging consensus."""

    desk: Literal[DeskType.CONTRARIAN] = DeskType.CONTRARIAN
    consensus_challenged: str | None = None
    contrarian_thesis: str | None = None


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------

AnyAssessment = Annotated[
    Annotated[TrendAssessment, Tag(DeskType.TREND)]
    | Annotated[VolatilityAssessment, Tag(DeskType.VOLATILITY)]
    | Annotated[FlowAssessment, Tag(DeskType.FLOW)]
    | Annotated[FundamentalAssessment, Tag(DeskType.FUNDAMENTAL)]
    | Annotated[RiskDeskAssessment, Tag(DeskType.RISK)]
    | Annotated[ContrarianAssessment, Tag(DeskType.CONTRARIAN)],
    Discriminator("desk"),
]


# ---------------------------------------------------------------------------
# Position recommendation & result
# ---------------------------------------------------------------------------


class PositionRecommendation(BaseModel):
    """Final synthesis output — a specific option position with entry/exit criteria."""

    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float
    recommended_contract: str  # e.g., "AAPL 190C 2026-04-18"
    entry_price: Decimal
    entry_criteria: str
    exit_criteria: str
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    position_size_pct: float
    position_rationale: str
    risk_reward_ratio: float
    max_loss_estimate: str
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str
    summary: str
    key_factors: list[str]
    risk_assessment: str
    agent_agreement_score: float | None = None
    dissenting_desks: list[DeskType] = Field(default_factory=list)
    model_used: str

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        return validate_unit_interval(v, "confidence")

    @field_validator("position_size_pct")
    @classmethod
    def _validate_position_size_pct(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"position_size_pct must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"position_size_pct must be in [0, 1], got {v}")
        return v

    @field_validator("risk_reward_ratio")
    @classmethod
    def _validate_risk_reward_ratio(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"risk_reward_ratio must be finite, got {v}")
        if v <= 0:
            raise ValueError(f"risk_reward_ratio must be > 0, got {v}")
        return v

    @field_validator("agent_agreement_score")
    @classmethod
    def _validate_agent_agreement_score(cls, v: float | None) -> float | None:
        if v is not None:
            return validate_unit_interval(v, "agent_agreement_score")
        return v

    @field_validator("key_factors")
    @classmethod
    def _validate_key_factors(cls, v: list[str]) -> list[str]:
        return validate_non_empty_list(v, "key_factors")

    @field_serializer("entry_price")
    def _serialize_entry_price(self, v: Decimal) -> str:
        return str(v)

    @field_serializer("stop_loss", "take_profit")
    def _serialize_optional_decimal(self, v: Decimal | None) -> str | None:
        return str(v) if v is not None else None


class RecommendationResult(BaseModel):
    """Complete recommendation output wrapping context, assessments, and recommendation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    context: MarketContext
    assessments: list[AnyAssessment]
    recommendation: PositionRecommendation
    total_usage: RunUsage
    duration_ms: int
    is_fallback: bool
    citation_density: float = 0.0

    @field_validator("citation_density")
    @classmethod
    def _validate_citation_density(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError(f"citation_density must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"citation_density must be >= 0, got {v}")
        return v
