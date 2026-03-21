"""Options Arena — Recommendation models for unified agent system.

DomainAssessment hierarchy with 6 desk-specific subclasses and discriminated
union for polymorphic JSON round-trip. All models are frozen snapshots.
"""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Tag, field_validator

from options_arena.models._validators import validate_non_empty_list, validate_unit_interval
from options_arena.models.enums import (
    DeskType,
    IVTermStructureShape,
    SignalDirection,
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
