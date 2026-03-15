"""Valuation models for multi-methodology equity valuation.

Two frozen Pydantic v2 models for the 4-model composite valuation framework:
  ValuationModelResult  -- per-model fair value estimate with data quality notes.
  CompositeValuation    -- aggregated composite with margin of safety and signal.

All models are pure data definitions with no business logic, no I/O.
"""

import math
from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models._validators import validate_unit_interval
from options_arena.models.enums import ValuationSignal


class ValuationModelResult(BaseModel):
    """Single valuation model output.

    Frozen (immutable after construction) -- represents a completed model estimate.
    ``fair_value`` and ``margin_of_safety`` are ``None`` when data is insufficient.
    ``confidence`` is a data quality score in [0.0, 1.0].
    """

    model_config = ConfigDict(frozen=True)

    methodology: str  # "owner_earnings_dcf", "three_stage_dcf", etc.
    fair_value: float | None  # per-share estimate, None if data insufficient
    margin_of_safety: float | None  # (fair - price) / fair
    confidence: float  # [0.0, 1.0] data quality score
    data_quality_notes: list[str]

    @field_validator("fair_value")
    @classmethod
    def validate_fair_value(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on fair_value while allowing None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"fair_value must be finite, got {v}")
        return v

    @field_validator("margin_of_safety")
    @classmethod
    def validate_margin_of_safety(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on margin_of_safety while allowing None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"margin_of_safety must be finite, got {v}")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")


class CompositeValuation(BaseModel):
    """Aggregated valuation from up to four independent models.

    Frozen (immutable after construction) -- represents a completed valuation snapshot.
    ``composite_fair_value`` is ``None`` when all four models lack sufficient data.
    ``computed_at`` must be UTC.
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    current_price: float
    composite_fair_value: float | None
    composite_margin_of_safety: float | None
    valuation_signal: ValuationSignal | None
    models: list[ValuationModelResult]
    weights_used: dict[str, float]
    computed_at: datetime  # UTC validated

    @field_validator("current_price")
    @classmethod
    def validate_current_price(cls, v: float) -> float:
        """Ensure current_price is finite and positive."""
        if not math.isfinite(v):
            raise ValueError(f"current_price must be finite, got {v}")
        if v < 0.0:
            raise ValueError(f"current_price must be >= 0, got {v}")
        return v

    @field_validator("composite_fair_value")
    @classmethod
    def validate_composite_fair_value(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on composite_fair_value while allowing None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"composite_fair_value must be finite, got {v}")
        return v

    @field_validator("composite_margin_of_safety")
    @classmethod
    def validate_composite_margin_of_safety(cls, v: float | None) -> float | None:
        """Reject NaN/Inf on composite_margin_of_safety while allowing None."""
        if v is not None and not math.isfinite(v):
            raise ValueError(f"composite_margin_of_safety must be finite, got {v}")
        return v

    @field_validator("computed_at")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        """Ensure computed_at is UTC."""
        if v.tzinfo is None or v.utcoffset() != timedelta(0):
            raise ValueError("computed_at must be UTC")
        return v
