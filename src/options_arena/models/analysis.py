"""Analysis models for Options Arena.

Three models for market analysis and (v2) AI debate:
  MarketContext   -- flat snapshot of ticker state for analysis and debate agents.
  AgentResponse   -- structured response from a debate agent (frozen).
  TradeThesis     -- final trade recommendation from the debate (frozen).

``MarketContext`` is intentionally flat (not nested) because agents parse flat
text better than nested objects.  ``AgentResponse`` and ``TradeThesis`` define
shapes for the v2 debate system -- defined now, used later.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from options_arena.models.enums import (
    ExerciseStyle,
    MacdSignal,
    SignalDirection,
    SpreadType,
)


class MarketContext(BaseModel):
    """Snapshot of ticker state for analysis and (v2) debate agents.

    Keep flat -- agents parse flat text better than nested objects.
    NOT frozen: mutable so fields can be populated incrementally.

    ``Decimal`` fields use ``field_serializer`` to prevent float precision loss
    in JSON serialization.
    """

    ticker: str
    current_price: Decimal
    price_52w_high: Decimal
    price_52w_low: Decimal
    iv_rank: float
    iv_percentile: float
    atm_iv_30d: float
    rsi_14: float
    macd_signal: MacdSignal
    put_call_ratio: float
    next_earnings: date | None
    dte_target: int
    target_strike: Decimal
    target_delta: float
    sector: str
    dividend_yield: float  # decimal fraction (0.005 = 0.5%), from TickerInfo
    exercise_style: ExerciseStyle  # for pricing dispatch (BAW vs BSM)
    data_timestamp: datetime

    @field_validator("data_timestamp")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure data_timestamp is timezone-aware (UTC)."""
        if v.tzinfo is None:
            raise ValueError("data_timestamp must be timezone-aware (UTC)")
        return v

    @field_serializer("current_price", "price_52w_high", "price_52w_low", "target_strike")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)


class AgentResponse(BaseModel):
    """Structured response from a debate agent.

    Frozen (immutable after construction) -- represents a completed agent output.
    ``confidence`` is validated to be within [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    agent_name: str  # "bull", "bear", "risk"
    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    argument: str
    key_points: list[str]
    risks_cited: list[str]
    contracts_referenced: list[str]  # specific strikes/expirations
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within [0.0, 1.0]."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v


class TradeThesis(BaseModel):
    """Final trade recommendation produced by the debate system.

    Frozen (immutable after construction) -- represents a completed verdict.
    ``confidence`` is validated to be within [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float  # 0.0 to 1.0
    summary: str
    bull_score: float
    bear_score: float
    key_factors: list[str]
    risk_assessment: str
    recommended_strategy: SpreadType | None = None

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is within [0.0, 1.0]."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v
