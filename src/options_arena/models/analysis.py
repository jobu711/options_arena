"""Analysis models for Options Arena.

Four models for market analysis and AI debate:
  MarketContext      -- flat snapshot of ticker state for analysis and debate agents.
  AgentResponse      -- structured response from a debate agent (frozen).
  TradeThesis        -- final trade recommendation from the debate (frozen).
  VolatilityThesis   -- structured output from the Volatility Agent (frozen).

``MarketContext`` is intentionally flat (not nested) because agents parse flat
text better than nested objects.  ``AgentResponse``, ``TradeThesis``, and
``VolatilityThesis`` define shapes for the debate system.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator, model_validator

from options_arena.models.enums import (
    ExerciseStyle,
    MacdSignal,
    SignalDirection,
    SpreadType,
    VolAssessment,
)

logger = logging.getLogger(__name__)


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

    # Scoring context (from TickerScore)
    composite_score: float = 0.0
    direction_signal: SignalDirection = SignalDirection.NEUTRAL

    # Key indicators (normalized 0-100, None = not computed)
    adx: float | None = None
    sma_alignment: float | None = None
    bb_width: float | None = None
    atr_pct: float | None = None
    stochastic_rsi: float | None = None
    relative_volume: float | None = None

    # Greeks beyond delta (from first recommended contract)
    target_gamma: float | None = None
    target_theta: float | None = None  # $/day time decay
    target_vega: float | None = None  # $/1% IV change
    target_rho: float | None = None

    # Contract pricing
    contract_mid: Decimal | None = None  # mid price of recommended contract

    @field_validator("data_timestamp")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure data_timestamp is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("data_timestamp must be UTC")
        return v

    @field_serializer("current_price", "price_52w_high", "price_52w_low", "target_strike")
    def serialize_decimal(self, v: Decimal) -> str:
        """Serialize Decimal fields to str to avoid float precision loss in JSON."""
        return str(v)

    @field_serializer("contract_mid")
    def serialize_contract_mid(self, v: Decimal | None) -> str | None:
        """Serialize optional Decimal to str for JSON precision safety."""
        return str(v) if v is not None else None


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
        """Ensure confidence is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("key_points")
    @classmethod
    def validate_key_points(cls, v: list[str]) -> list[str]:
        """Ensure at least one key point is cited."""
        if len(v) < 1:
            raise ValueError("key_points must have at least 1 item")
        return v

    @field_validator("risks_cited")
    @classmethod
    def validate_risks_cited(cls, v: list[str]) -> list[str]:
        """Ensure at least one risk is cited."""
        if len(v) < 1:
            raise ValueError("risks_cited must have at least 1 item")
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
        """Ensure confidence is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("bull_score", "bear_score")
    @classmethod
    def validate_scores(cls, v: float) -> float:
        """Ensure bull/bear scores are finite and within [0.0, 10.0]."""
        if not math.isfinite(v):
            raise ValueError(f"score must be finite, got {v}")
        if not 0.0 <= v <= 10.0:
            raise ValueError(f"score must be in [0, 10], got {v}")
        return v

    @field_validator("key_factors")
    @classmethod
    def validate_key_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one key factor is cited."""
        if len(v) < 1:
            raise ValueError("key_factors must have at least 1 item")
        return v

    @model_validator(mode="after")
    def clamp_confidence_on_mismatch(self) -> TradeThesis:
        """Warn and clamp confidence when scores contradict direction.

        Uses ``object.__setattr__`` to mutate the frozen instance during validation —
        this is the standard Pydantic v2 pattern for frozen model validators.
        """
        clamped = self.confidence
        reason = ""

        if (
            self.bull_score > self.bear_score
            and self.direction == SignalDirection.BEARISH
            and self.confidence > 0.5
        ):
            clamped = 0.5
            reason = (
                f"bull_score ({self.bull_score}) > bear_score ({self.bear_score}) "
                f"but direction is BEARISH"
            )
        elif (
            self.bear_score > self.bull_score
            and self.direction == SignalDirection.BULLISH
            and self.confidence > 0.5
        ):
            clamped = 0.5
            reason = (
                f"bear_score ({self.bear_score}) > bull_score ({self.bull_score}) "
                f"but direction is BULLISH"
            )

        if max(self.bull_score, self.bear_score) < 4.0 and self.confidence > 0.5:
            clamped = min(clamped, 0.5)
            reason = reason or f"max score ({max(self.bull_score, self.bear_score)}) < 4.0"

        if clamped < self.confidence:
            logger.warning(
                "Clamping confidence for %s from %.2f to %.2f: %s",
                self.ticker,
                self.confidence,
                clamped,
                reason,
            )
            object.__setattr__(self, "confidence", clamped)
        return self


class VolatilityThesis(BaseModel):
    """Structured output from the Volatility Agent.

    Frozen (immutable after construction) -- represents a completed vol assessment.
    ``confidence`` is validated to be within [0.0, 1.0] with ``math.isfinite()`` guard.
    """

    model_config = ConfigDict(frozen=True)

    iv_assessment: VolAssessment
    iv_rank_interpretation: str  # Human-readable IV rank context
    confidence: float  # 0.0 to 1.0
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str
    target_iv_entry: float | None = None
    target_iv_exit: float | None = None
    suggested_strikes: list[str]
    key_vol_factors: list[str]
    model_used: str

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        if not math.isfinite(v):
            raise ValueError(f"confidence must be finite, got {v}")
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence must be in [0, 1], got {v}")
        return v

    @field_validator("target_iv_entry", "target_iv_exit")
    @classmethod
    def validate_iv_target(cls, v: float | None) -> float | None:
        """Ensure IV targets are finite and non-negative when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"IV target must be finite, got {v}")
            if v < 0.0:
                raise ValueError(f"IV target must be >= 0.0, got {v}")
        return v

    @field_validator("key_vol_factors")
    @classmethod
    def validate_key_vol_factors(cls, v: list[str]) -> list[str]:
        """Ensure at least one volatility factor is cited."""
        if len(v) < 1:
            raise ValueError("key_vol_factors must have at least 1 item")
        return v
