"""Dimensional scoring models for the Deep Signal Engine.

DimensionalScores -- 8 per-family sub-scores replacing the single composite.
DirectionSignal  -- continuous direction confidence with contributing signals.
"""

import math

from pydantic import BaseModel, ConfigDict, field_validator

from options_arena.models._validators import validate_non_empty_list, validate_unit_interval
from options_arena.models.enums import SignalDirection


class DimensionalScores(BaseModel):
    """8 per-family sub-scores computed from IndicatorSignals.

    Each family score is float | None:
    - None when ALL indicators in the family are missing
    - float (0.0-100.0) when at least one indicator is present

    Frozen -- represents a completed scoring snapshot.
    """

    model_config = ConfigDict(frozen=True)

    trend: float | None = None
    iv_vol: float | None = None
    hv_vol: float | None = None
    flow: float | None = None
    microstructure: float | None = None
    fundamental: float | None = None
    regime: float | None = None
    risk: float | None = None

    @field_validator(
        "trend", "iv_vol", "hv_vol", "flow", "microstructure", "fundamental", "regime", "risk"
    )
    @classmethod
    def validate_score_range(cls, v: float | None) -> float | None:
        """Ensure each score is finite and within [0, 100] when provided."""
        if v is not None:
            if not math.isfinite(v):
                raise ValueError(f"score must be finite, got {v}")
            if not 0.0 <= v <= 100.0:
                raise ValueError(f"score must be in [0, 100], got {v}")
        return v


class DirectionSignal(BaseModel):
    """Continuous direction confidence with contributing signal breakdown.

    Replaces discrete 3-class SignalDirection with a richer signal
    that preserves the direction but adds continuous confidence and
    a list of the signals that contributed to the direction call.

    Frozen -- represents a completed direction assessment.
    """

    model_config = ConfigDict(frozen=True)

    direction: SignalDirection
    confidence: float  # 0.0-1.0
    contributing_signals: list[str]

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Ensure confidence is finite and within [0.0, 1.0]."""
        return validate_unit_interval(v, "confidence")

    @field_validator("contributing_signals")
    @classmethod
    def validate_contributing_signals(cls, v: list[str]) -> list[str]:
        """Ensure at least one contributing signal is present."""
        return validate_non_empty_list(v, "contributing_signals")
